"""A stock that empties and that moves refill: exact faces, conservation and thresholds.

The service delivers 1 person an hour from its stock to a tally of the people served, beside a
warehouse of 20 people. Local sharing gives the outflow of an empty stock what flows in, so the
delivery stops when the stock is empty and starts again when a move refills it (`timeline/moment.py`
builds the set again at the move). Expected stocks and tallies are constant-rate arithmetic worked
by hand.
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    BOOL,
    Builder,
    add,
    after,
    assign,
    count,
    event,
    flow,
    formula,
    ifelse,
    move,
    q,
    reset_when,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request

UNITS = {'h': {'time': 1}, 'person': {'people': 1}}
PERSON_H = q(1, 'person/h')


def service(*parts, stock=5, request=PERSON_H, horizon=12):
    """The service with its parts; the program and the record of its run."""
    b = Builder(UNITS)
    b.entity(
        'service',
        value('stock', 'person', stock, lower=0, scale=10),
        value('served', 'person', 0, lower=0, scale=10),
        value('warehouse', 'person', 20, lower=0, scale=20),
        value('on', BOOL, True),
        value('noticed', '', 0),
        flow('serve', this.stock, this.served, request=request),
        *parts,
    )
    program = b.finish()
    return program, run(program, Configuration(Request(horizon)))


def at_time(name, hours, *body):
    """An event that a clock starts once, at `hours`, and whose stage runs `body` then."""
    return event(
        name,
        when(t >= q(hours, 'h'), start(getattr(this, name)), reset=reset_when(False)),
        after(q(0, 'h'), *body),
    )


def notice(test, reset=None):
    """An event that its trigger starts on `test`, and that counts its starts."""
    return event(
        'notice', when(test, start(this.notice), reset=reset), after(q(0, 'h'), add(this.noticed, 1))
    )


def values(program, record, times):
    names = ['service.stock', 'service.served', 'service.warehouse']
    return [reading.values for reading in read(record, program, names, list(times))]


def test_an_empty_stock_and_two_refills_preserve_the_mass():
    # 5 people at 1 an hour: empty at 5 h; 2 people moved in at 8 h last until 10 h, 1 at 11 h until
    # 12 h. A trigger with no reset rearms when the stock holds any, so it notices each emptying.
    program, record = service(
        notice(this.stock <= q(0, 'person')),
        at_time('refill_1', 8, move(q(2, 'person'), this.warehouse, this.stock)),
        at_time('refill_2', 11, move(q(1, 'person'), this.warehouse, this.stock)),
    )
    assert record.failure is None, record.failure
    assert [entry.t for entry in record.entries('fire', 'service.notice.when[0]')] == pytest.approx(
        [5, 10, 12]
    )
    cases = ((5, 0, 5), (8.5, 1.5, 5.5), (10, 0, 7), (11.5, 0.5, 7.5), (12, 0, 8))
    stock, served, warehouse = values(program, record, (at for at, _, _ in cases))
    for k, (_, remaining, done) in enumerate(cases):
        assert stock[k] == pytest.approx(remaining, abs=1e-10)
        assert served[k] == pytest.approx(done, abs=1e-10)
        assert warehouse[k] + stock[k] + served[k] == pytest.approx(25, abs=1e-10)


def test_a_zero_threshold_waits_for_a_discrete_activation():
    # The stock is empty from the start; the trigger also needs an activation, which a clock starts
    # at 3 h and which turns the service off: it fires then, once.
    _, record = service(
        at_time('activate', 3, assign(this.on, False)),
        notice((this.stock <= q(0, 'person')) & (count(this.activate.occurrences) > 0) & ~this.on),
        stock=0,
        request=q(0, 'person/h'),
    )
    assert [entry.t for entry in record.entries('fire', 'service.notice.when[0]')] == [3]
    assert [entry.t for entry in record.entries('start', 'service.activate')] == [3]


def test_a_positive_threshold_keeps_its_remaining_stock():
    # The delivery runs while the service is on; a trigger at 2 people turns it off, at 3 h.
    program, record = service(
        event(
            'stop',
            when(this.stock <= q(2, 'person'), start(this.stop), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.on, False)),
        ),
        request=formula(ifelse(this.on, PERSON_H, q(0, 'person/h'))),
    )
    (at,) = [entry.t for entry in record.entries('fire', 'service.stop.when[0]')]
    assert at == pytest.approx(3, abs=1e-8)
    times = (1, 3, 6, 12)
    stock, served, warehouse = values(program, record, times)
    for k, hours in enumerate(times):
        assert stock[k] == pytest.approx(max(2, 5 - hours), abs=1e-8)
        assert served[k] == pytest.approx(min(3, hours), abs=1e-8)
        assert warehouse[k] + stock[k] + served[k] == pytest.approx(25, abs=1e-10)


@pytest.mark.parametrize(
    'make',
    [
        lambda: this.stock > q(0, 'person'),
        lambda: this.stock != q(0, 'person'),
        lambda: ~(this.stock <= q(0, 'person')),
    ],
    ids=['above', 'unequal', 'not at most'],
)
def test_a_strict_presence_of_a_moving_stock_has_no_first_instant(make):
    # The stock falls from 5 people: `stock > 0` holds from the start and becomes false at 5 h, with
    # no last instant at which it holds; a trigger on it is a diagnostic, never polled.
    _, record = service(notice(make()))
    assert 'strict threshold' in record.failure.detail('message')
    assert record.failure.t == 0
