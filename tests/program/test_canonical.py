"""Canonical bytes (`napkin/program/canonical.py`), which the key of a stored run reads.

Two builds of one model give equal bytes, also with the rows of its tables in another order; a change
of a number, a unit, a name or the structure gives other bytes. A configuration's bytes leave out the
request (what to record, and the horizon) and keep everything that a run computes from.
"""

from dataclasses import replace

import pytest

from napkin.program.build import SINK, Builder, flow, q, value
from napkin.program.canonical import configuration_bytes, program_bytes
from napkin.program.config import (
    SAMPLED,
    Budgets,
    Configuration,
    InputValue,
    Limits,
    Numerics,
    Quantity,
    Request,
)
from napkin.program.record import Key

from .examples import EXAMPLES, PLACES, ROUTES, UNITS, network_program


@pytest.mark.parametrize('name', sorted(EXAMPLES))
def test_two_builds_of_one_model_give_equal_bytes(name):
    first, second = EXAMPLES[name](), EXAMPLES[name]()
    assert program_bytes(first.program) == program_bytes(second.program)
    assert configuration_bytes(first.configuration) == configuration_bytes(second.configuration)


def test_a_reordered_table_gives_equal_bytes():
    """Spec, "Worked network data and expected rates": reordering places.csv or routes.csv, or both,
    without editing a link cell, changes no named result. The rows are kept in the order of their
    ids and the links name rows, so the program is the same."""
    original = program_bytes(network_program())
    assert program_bytes(network_program(places=PLACES[::-1])) == original
    assert program_bytes(network_program(routes=ROUTES[::-1])) == original
    assert program_bytes(network_program(places=PLACES[1:] + PLACES[:1], routes=ROUTES[::-1])) == original


def tank(water=8, unit='L', name='water', capacity=5, upper=None):
    """The spec's tank and its clinic, with one thing changed."""
    b = Builder(UNITS)
    store = b.entity('tank', value(name, unit, water, lower=0, upper=upper))
    rate = f'{unit}/h'
    b.entity(
        'clinic', flow('delivery', getattr(store, name), SINK, capacity=q(capacity, rate), request=q(3, rate))
    )
    return b.finish()


def test_a_change_gives_other_bytes():
    variants = [
        tank(),
        tank(water=9),
        tank(unit='g'),
        tank(name='stock'),
        tank(capacity=6),
        tank(upper=20),
    ]
    found = [program_bytes(program) for program in variants]
    assert len(set(found)) == len(found)


def test_a_change_of_the_kind_of_a_number_gives_other_bytes():
    """An int, a float and a fraction are three numbers to the key, as they are three constants to
    `napkin/core`: the bytes never take one for another."""
    assert program_bytes(tank(water=8)) != program_bytes(tank(water=8.0))


def test_the_bytes_of_a_configuration_leave_out_the_request():
    plain = Configuration(Request(1))
    asked = Configuration(Request(5, everything=False, keys=(Key('tank', ('water',)),)))
    assert configuration_bytes(plain) == configuration_bytes(asked)


def test_a_change_of_a_configuration_gives_other_bytes():
    request = Request(1)
    variants = [
        Configuration(request),
        Configuration(request, mode=SAMPLED, seed=1),
        Configuration(request, mode=SAMPLED, seed=2),
        Configuration(request, inputs=(InputValue('tank', 'water', Quantity(9, 'L')),)),
        Configuration(request, inputs=(InputValue('tank', 'water', Quantity(9, 'g')),)),
        Configuration(request, limits=Limits(max_rounds=10)),
        Configuration(request, budgets=Budgets(fair_programs=5)),
        Configuration(request, numerics=Numerics(rtol=1e-6)),
    ]
    found = [configuration_bytes(configuration) for configuration in variants]
    assert len(set(found)) == len(found)


def test_a_value_with_no_canonical_bytes_is_refused():
    with pytest.raises(TypeError):
        program_bytes(replace(tank(), root=(object(),)))
