"""Analytic witnesses of empty stocks that depart their face, and of thresholds that the triggers watch.

A warehouse of 20 people supplies a service's stock at 2 people an hour, from the start or from 4 h
when a clock turns the supply on, and the service delivers 1 person an hour to a tally. Local sharing
gives the outflow of an empty stock what flows in, so an empty stock that receives more than it
delivers leaves its face at once, and holds at it while it receives less. The expected values and
times are constant-rate arithmetic worked by hand.
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    BOOL,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    event,
    flow,
    formula,
    ifelse,
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


def rate(number):
    return q(number, 'person/h')


def at_time(name, hours, *body):
    """An event that a clock starts once, at `hours`, and whose stage runs `body` then."""
    return event(
        name,
        when(t >= q(hours, 'h'), start(getattr(this, name)), reset=reset_when(False)),
        after(q(0, 'h'), *body),
    )


def watch(test):
    """An event that its trigger starts once, when `test` first holds."""
    return event(
        'watch', when(test, start(this.watch), reset=reset_when(False)), after(q(0, 'h'), add(this.seen, 1))
    )


def run_of(*parts, horizon=12):
    b = Builder(UNITS)
    b.entity('service', *parts)
    program = b.finish()
    return program, run(program, Configuration(Request(horizon)))


def supplied_empty_stock(*parts, delayed=False, serve=True):
    """An empty stock that the warehouse supplies at 2 people an hour, from the start or from 4 h,
    and that delivers 1 person an hour to the tally when `serve`."""
    return (
        value('stock', 'person', 0, lower=0, scale=10),
        value('served', 'person', 0, lower=0, scale=10),
        value('warehouse', 'person', 20, lower=0, scale=20),
        value('on', BOOL, not delayed),
        # A request is soft (D15): the supply's capacity keeps it at its request, or closed.
        flow(
            'supply',
            this.warehouse,
            this.stock,
            request=rate(2),
            capacity=formula(ifelse(this.on, rate(2), rate(0))),
        ),
        *((flow('serve', this.stock, this.served, request=rate(1)),) if serve else ()),
        *((at_time('opening', 4, assign(this.on, True)),) if delayed else ()),
        *parts,
    )


@pytest.mark.parametrize('delayed', [False, True])
def test_an_empty_stock_that_receives_more_than_it_delivers_leaves_its_face(delayed):
    program, record = run_of(*supplied_empty_stock(delayed=delayed))
    assert record.failure is None, record.failure
    offset = 4 if delayed else 0
    # While the warehouse supplies: W' = -2, S' = 2 - 1, C' = 1. After the warehouse is empty, at an
    # exposure of 10 h: S' = -1, C' = 1.
    times = (offset, offset + 0.5, offset + 2, offset + 5, 12)
    names = ['service.warehouse', 'service.stock', 'service.served']
    warehouse, stock, served = (reading.values for reading in read(record, program, names, list(times)))
    for k, hours in enumerate(times):
        exposure = max(0, hours - offset)
        expected_warehouse = max(0, 20 - 2 * exposure)
        assert warehouse[k] == pytest.approx(expected_warehouse, abs=2e-7)
        assert served[k] == pytest.approx(exposure, abs=2e-7)
        assert stock[k] == pytest.approx(20 - expected_warehouse - exposure, abs=2e-7)
        assert warehouse[k] + stock[k] + served[k] == pytest.approx(20, abs=1e-10)


def test_a_departure_from_a_face_goes_on_through_an_empty_stock_downstream():
    # The stock receives 2 and delivers 1.99999999 into a second stock, which delivers 0.5: the stock
    # rises at 1e-8 people an hour, the second at 1.49999999.
    parts = supplied_empty_stock(
        value('second', 'person', 0, lower=0, scale=10),
        flow('serve', this.stock, this.second, request=rate(1.99999999)),
        flow('finish', this.second, this.served, request=rate(0.5)),
        serve=False,
    )
    program, record = run_of(*parts, horizon=1)
    times = [0.25, 0.5, 1.0]
    names = ['service.stock', 'service.second', 'service.served', 'service.warehouse']
    stock, second, served, warehouse = (reading.values for reading in read(record, program, names, times))
    for k, hours in enumerate(times):
        assert stock[k] == pytest.approx(1e-8 * hours, abs=2e-9)
        assert second[k] == pytest.approx(1.49999999 * hours, abs=2e-7)
        assert served[k] == pytest.approx(0.5 * hours, abs=2e-7)
        assert stock[k] + second[k] + served[k] + warehouse[k] == pytest.approx(20, abs=1e-10)


def test_a_fast_affine_threshold_is_located_inside_the_crossing_tolerance():
    # S(t) = 1e10 t reaches 1 person at 1e-10 h; the firing turns the supply off, so S stays 1.
    program, record = run_of(
        value('stock', 'person', 0, lower=0, scale=1),
        value('on', BOOL, True),
        value('seen', '', 0),
        flow('supply', SOURCE, this.stock, request=formula(ifelse(this.on, rate(1e10), rate(0)))),
        event(
            'enough',
            when(this.stock >= q(1, 'person'), start(this.enough), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.on, False)),
        ),
        horizon=1,
    )
    (at,) = [entry.t for entry in record.entries('fire', 'service.enough.when[0]')]
    assert at == pytest.approx(1e-10, abs=1e-20)
    assert read(record, program, ['service.stock'], [1.0])[0].values[0] == pytest.approx(1, abs=1e-10)


def delivering(*parts, horizon=24):
    """10 people that the service delivers at 1 an hour: served(t) = t until the stock is empty at
    10 h."""
    return run_of(
        value('stock', 'person', 10, lower=0, scale=10),
        value('served', 'person', 0, lower=0, scale=10),
        value('seen', '', 0),
        flow('serve', this.stock, this.served, request=rate(1)),
        *parts,
        horizon=horizon,
    )


@pytest.mark.parametrize(('threshold', 'expected'), [(3, 5.0), (7, 7.0)])
def test_a_crossing_with_a_clock_happens_at_the_clock_or_at_the_first_crossing_after_it(threshold, expected):
    """The clock holds from 5 h, and served(5) = 5: a threshold of 3 already holds then, so the
    trigger fires at 5 h; a threshold of 7 is crossed after it, where served(t) = 7."""
    _, record = delivering(watch((this.served >= q(threshold, 'person')) & (t >= q(5, 'h'))))
    assert [entry.t for entry in record.entries('fire', 'service.watch.when[0]')] == pytest.approx(
        [expected], abs=1e-8
    )


def test_a_discrete_gate_observes_a_threshold_crossed_before_it_opens():
    # The stock is empty from 10 h; a flag that a clock sets at 12 h opens the gate of the trigger,
    # which then finds the threshold already crossed and fires at 12 h.
    program, record = delivering(
        value('flag', BOOL, False),
        at_time('open_gate', 12, assign(this.flag, True)),
        watch((this.stock <= q(0, 'person')) & this.flag),
    )
    assert [entry.t for entry in record.entries('fire', 'service.watch.when[0]')] == [12]
    stock, served = read(record, program, ['service.stock', 'service.served'], [10.0, 24.0])
    assert stock.values[0] == 0 and served.values[1] == pytest.approx(10)
