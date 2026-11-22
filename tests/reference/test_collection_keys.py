"""Natural collection keys and equal-key selection through compiled public programs."""

import pytest

from napkin.model.compile import compile_text
from napkin.program.build import SINK, Builder, flow, formula, q, this, value
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
CONFIG = Configuration(Request(1))


def picked_at_start(program):
    run, failure = run_of(program, CONFIG)
    assert failure is None, failure
    return value_at(run, program, Key('', ('picked',)), 0)


def member_program(collection, cursor):
    # A stored key keeps the lookup in the program: the compiler can fold literal keys.
    source = f"""Other:
    weight: number = 99
unrelated: Other
Member:
    weight: number = 2
    rank: number = 0
first: Member
second: Member
    weight = 8
cursor: number = {cursor}
picked = formula({collection}.at(cursor).weight)
"""
    return compile_text(source, UNITS).program


@pytest.mark.parametrize('collection', ['Member.instances', '<second, first>'])
@pytest.mark.parametrize('key, expected', [(0, 2), (1, 8)])
def test_entity_creation_numbers_start_at_zero_within_each_template(collection, key, expected):
    assert picked_at_start(member_program(collection, key)) == expected


def test_an_equal_explicit_key_picks_the_later_created_member():
    assert picked_at_start(member_program('Member.instances.by(rank)', 0)) == 8


@pytest.mark.parametrize('key, expected', [(0, 2), (1, 8)])
def test_endpoint_flows_have_zero_based_creation_keys(key, expected):
    builder = Builder(UNITS)
    box = builder.entity(
        'box',
        value('stock', 'L', 20),
        flow('early', this.stock, SINK, request=q(2, 'L/h')),
        flow('late', this.stock, SINK, request=q(8, 'L/h')),
    )
    builder.root(value('picked', 'L/h', formula(box.stock.outflow.flows.at(key).actual_rate)))
    assert picked_at_start(builder.finish()) == expected
