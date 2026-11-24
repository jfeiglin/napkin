"""A contact batch has one stock-key order for settlement and for the trace."""

import math
from decimal import Decimal
from fractions import Fraction
from itertools import permutations

from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.contacts import contact_batch
from napkin.engine.timeline.way import Way
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint
from napkin.program.config import Configuration, Request
from tests.comparison_bands import band_samples

TEMPLATE = """scenario "Coupled stock contacts"
    horizon 2 h
yard:
{}
    clock = event():
        after 1 h
yard.clock.start()
"""

# At 1 L/h, this amount is just beyond one hour's delivery, inside the stock's band.
(UNIT_BAND,) = band_samples(Configuration(Request(2)), 1, multiples=(1,))
CONTACT_LEVEL = 1 + Decimal(str(UNIT_BAND)) / 100

SPLIT = f"""    a: L = {4 * CONTACT_LEVEL} L in [0 L,]
    b: L = {CONTACT_LEVEL} L in [0 L,]
    c: L = 0 L in [0 L,{5 * CONTACT_LEVEL} L]
    flow ab: this.a -> this.b
        request = 1 L/h
    flow ac: this.a -> this.c
        request = 3 L/h
    flow bc: this.b -> this.c
        request = 2 L/h"""

CAPPED = f"""    feeder: L = 8 L in [0 L,]
    a: L = 0 L in [0 L,{CONTACT_LEVEL} L]
    b: L = 0 L in [0 L,{CONTACT_LEVEL} L]
    flow pipe_a: this.feeder -> this.a
        request = 1 L/h
        capacity = 1 L/h
    flow pipe_b: this.feeder -> this.b
        request = 1 L/h
        capacity = 1 L/h"""


def batch_results(monkeypatch, source, contacts, pipes):
    model = compile_text(TEMPLATE.format(source), {'h': {'time': 1}, 'L': {'volume': 1}})
    incoming = Way.contacts_at
    for order in permutations(contacts):
        seen = []

        def permuted(way, at, through):
            rows = list(incoming(way, at, through))
            if len(rows) == len(order) and {name for _, name, _ in rows} == set(order):
                seen.append(order)
                return sorted(rows, key=lambda row: order.index(row[1]))
            return rows

        with monkeypatch.context() as patch:
            patch.setattr(Way, 'contacts_at', permuted)
            machine = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.clock.step[0]'),))
            stopped = machine.run()
        assert seen and isinstance(stopped, Checkpoint) and stopped.stop.t == 1
        assert tuple(entry.part for entry in machine.recorder.trace if entry.kind == 'contact') == contacts
        levels = tuple(machine.stock_balance(name, 1) for name in contacts)
        amounts = tuple(machine.ways.instance_of(pipe).transferred(pipe, 1) for pipe in pipes)
        reasons = tuple(e.detail('reason') for e in machine.recorder.trace if e.detail('placements'))
        yield levels, amounts, reasons


def test_coupled_loop_uses_the_same_split_for_all_six_contact_orders(monkeypatch):
    contacts = ('yard.a', 'yard.b', 'yard.c')
    results = set(batch_results(monkeypatch, SPLIT, contacts, ('yard.ab', 'yard.ac', 'yard.bc')))
    (((a, b, c), (ab, ac, bc), reasons),) = results
    unit_delivery = Fraction(CONTACT_LEVEL)
    assert (a, b, c) == (0, 0, 5 * unit_delivery)
    assert ab + ac == 4 * unit_delivery
    assert bc - ab == unit_delivery
    assert not reasons


def test_both_contact_orders_report_the_same_refused_capacity(monkeypatch):
    results = set(batch_results(monkeypatch, CAPPED, ('yard.a', 'yard.b'), ('yard.pipe_a', 'yard.pipe_b')))
    ((levels, amounts, (reason,)),) = results
    assert levels == amounts == (1, 1)
    assert reason == 'the placement on yard.pipe_a at 1 h exceeds yard.pipe_a.capacity'


def test_coalesced_contacts_use_the_name_before_the_located_time():
    first = (1.0, 'b', 'lower bound')
    second = (math.nextafter(1.0, math.inf), 'a', 'upper bound')
    bounds = {'a': (0, 1), 'b': (0, 1)}
    for order in permutations((first, second)):
        trace, levels = contact_batch(bounds, order)
        assert trace == (second, first)
        assert tuple(levels.items()) == (('a', 1), ('b', 0))
