"""Projection preserves keys. A subsequent filter or key reads the projected flow."""

import pytest

from napkin.program import build as b
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at


def pump_program(selection):
    builder = b.Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    tank = builder.entity('tank', b.value('water', 'L', 40))
    pumps = builder.template(
        'Pump',
        b.input_('rank', '', 1),
        b.input_('rate', 'L/h', b.q(1, 'L/h')),
        b.value('water', 'L', 0),
        b.flow('pipe', tank.water, b.this.water, request=b.this.rate),
    )
    builder.member(pumps, 'left', rank=2)
    right = builder.member(pumps, 'right', rank=1, rate=b.q(2, 'L/h'))
    builder.root(b.value('rate', 'L/h', b.formula(selection(pumps.instances, right))))
    return builder.finish()


@pytest.mark.parametrize(
    'selection,expected',
    [
        pytest.param(
            lambda pumps, right: b.fsum(pumps.pipe.where(b.item.sink == right.water).actual_rate),
            2,
            id='filter-projected-flow-by-sink',
        ),
        pytest.param(
            lambda pumps, right: pumps.pipe.by('request').at(b.q(1, 'L/h')).actual_rate,
            1,
            id='key-projected-flow-by-request',
        ),
        pytest.param(
            lambda pumps, right: pumps.by('rank').pipe.at(1).actual_rate,
            2,
            id='preserve-pump-key-through-flow-projection',
        ),
    ],
)
def test_flow_projection_uses_the_member_at_each_operation(selection, expected):
    # Requests differ between pumps. The right pump is the first by rank and the last by request.
    program = pump_program(selection)
    result, failure = run_of(program, Configuration(Request(1)))
    assert failure is None, failure
    assert value_at(result, program, Key('', ('rate',)), 0) == expected
