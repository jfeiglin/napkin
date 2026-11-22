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


def member_program(collection, cursor, second_rank=0):
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
    rank = {second_rank}
cursor: number = {cursor}
picked = formula({collection}.at(cursor).weight)
"""
    return compile_text(source, UNITS).program


@pytest.mark.parametrize('collection', ['Member.instances', '<second, first>'])
@pytest.mark.parametrize('key, expected', [(0, 2), (1, 8)])
def test_entity_creation_numbers_start_at_zero_within_each_template(collection, key, expected):
    assert picked_at_start(member_program(collection, key)) == expected


@pytest.mark.parametrize('collection', ['Member.instances', '<first, second>', '<second, first>'])
def test_an_equal_explicit_key_picks_the_later_created_member(collection):
    assert picked_at_start(member_program(f'{collection}.by(rank)', 0)) == 8


@pytest.mark.parametrize('second_rank, key, expected', [(-1, 0, 2), (1, 0, 2), (1, 1, 8)])
def test_a_distinct_explicit_key_selects_the_greatest_eligible_key(second_rank, key, expected):
    assert picked_at_start(member_program('<second, first>.by(rank)', key, second_rank)) == expected


def test_simultaneously_started_occurrences_pick_the_later_creation():
    source = """box:
    visit = event(amount: number):
        after 1 h
box.visit.start(2)
box.visit.start(8)
picked = formula(box.visit.occurrences.at(0 h).amount)
"""
    assert picked_at_start(compile_text(source, UNITS).program) == 8


def flow_program(lookup):
    builder = Builder(UNITS)
    box = builder.entity(
        'box',
        value('stock', 'L', 20),
        flow('early', this.stock, SINK, request=q(8, 'L/h'), capacity=q(2, 'L/h')),
        flow('late', this.stock, SINK, request=q(8, 'L/h')),
    )
    builder.root(value('picked', 'L/h', formula(lookup(box.stock.outflow.flows).actual_rate)))
    return builder.finish()


@pytest.mark.parametrize('key, expected', [(0, 2), (1, 8)])
def test_endpoint_flows_have_zero_based_creation_keys(key, expected):
    assert picked_at_start(flow_program(lambda flows: flows.at(key))) == expected


def test_flows_with_equal_requests_pick_the_later_creation():
    assert picked_at_start(flow_program(lambda flows: flows.by('request').at(q(8, 'L/h')))) == 8
