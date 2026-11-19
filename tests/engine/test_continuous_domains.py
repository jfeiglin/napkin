"""Continuous domains between moments: an assertion over state is watched between moments, so a
breach inside a segment fails the run there and not at a sample of the report; a guard keeps the
side that it does not take unread, and a stage's expression is read only when the stage runs.

The transient queue oracle is the closed form for two sequential exponential stages, not a replay
of the engine or an exported reference trajectory.
"""

import math

import pytest
from scipy.optimize import brentq

from napkin.engine import read, run
from napkin.program.build import (
    Builder,
    after,
    assertion,
    assign,
    event,
    flow,
    formula,
    ifelse,
    q,
    start,
    t,
    this,
    value,
)
from napkin.program.config import Configuration, Request

UNITS = {'h': {'time': 1}, 'person': {'people': 1}}


def queue(check):
    """Ten people arrive in a queue at A / 1 h and leave it at W / 1 h; `check` is asserted."""
    b = Builder(UNITS)
    b.entity(
        'service',
        value('arrived', 'person', 10, lower=0),
        value('waiting', 'person', 0, lower=0),
        value('served', 'person', 0),
        flow('join', this.arrived, this.waiting, request=formula(this.arrived / q(1, 'h'))),
        flow('leave', this.waiting, this.served, request=formula(this.waiting / q(1, 'h'))),
        assertion(check(this)),
    )
    return run(b.finish(), Configuration(Request(12)))


def test_a_transient_breach_of_an_assertion_cannot_hide_inside_a_segment():
    # A' = -A, W' = A - W, A(0) = 10, W(0) = 0: W(t) = 10 t exp(-t), which peaks at 10/e at 1 h.
    # The assertion W <= 3 holds at 0 h and at 12 h and breaks inside. W rises and falls, and the
    # engine certifies its first contact step by step (PLAN, change 20): the run fails at the first
    # root of 10 t exp(-t) = 3, and never reports the 0 h and 12 h samples as if the assertion held.
    assert 10 / math.e > 3 > 120 * math.exp(-12)
    record = queue(lambda this: this.waiting <= q(3, 'person'))
    breach = brentq(lambda x: 10 * x * math.exp(-x) - 3, 0, 1, xtol=1e-14)
    assert record.failure.t == pytest.approx(breach, abs=1e-6)
    assert 'the assertion does not hold' in record.failure.detail('message')
    # The served count only rises: S(t) = 10 (1 - (1 + t) e^-t) reaches 9 at its one root.
    first = brentq(lambda x: 10 * (1 - (1 + x) * math.exp(-x)) - 9, 1, 12, xtol=1e-14)
    record = queue(lambda this: this.served <= q(9, 'person'))
    assert record.failure.t == pytest.approx(first, abs=1e-6)
    assert 'service.served' in record.failure.detail('message') or 'assertion' in record.failure.detail(
        'message'
    )


def test_a_guard_keeps_its_undefined_side_unread_and_a_stage_reads_its_expression_when_it_runs():
    """`n / stock` is read only while the stock holds something; the stage's `7 h / (t - 5 h)` is
    read at its one time, 12 h, and gives 1, though it has no value at 5 h."""
    b = Builder(UNITS)
    service = b.entity(
        'service',
        value('n', 'person', 10),
        value('stock', 'person', 0),
        value('safe_ratio', '', formula(ifelse(this.stock > q(0, 'person'), this.n / this.stock, 0))),
        value('checkpoint_ratio', '', 0),
        event('stop', after(q(12, 'h'), assign(this.checkpoint_ratio, q(7, 'h') / (t - q(5, 'h'))))),
    )
    b.setup(start(service.stop))
    program = b.finish()
    record = run(program, Configuration(Request(12)))
    assert record.failure is None
    found = read(record, program, ['service.safe_ratio', 'service.checkpoint_ratio'], [5, 12])
    assert [reading.values for reading in found] == [(0, 0), (0, 1)]
