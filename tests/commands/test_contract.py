"""The changes to the contract (`napkin/program/`) and to the engine that the switch of the first slice
made, each with its expected value worked by hand.

- `build.call` builds a function of the language's closed list, and `X(node, reads)` wraps a node
  that no operator makes;
- a flow between plain numbers has its rate in `1/h`, in the builder as in the front end;
- a curved piece of a record keeps its series in its own field, which the program's reader reads;
- a configuration may give an input in a unit of the library that the program does not spell;
- the engine locates a change to the crossing tolerance of the configuration (`Numerics.crossing`);
- a record that keeps only some values keeps what their formulas read, so `read` evaluates them.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from napkin.core import expr as nodes
from napkin.engine import read, run
from napkin.engine.continuous.integrate import STALLED_STEPS, Limit
from napkin.model.compile import compile_text, library_units
from napkin.model.library import empty_library
from napkin.program import build
from napkin.program.build import BOOL, SINK, Builder, X, flow, formula, input_, named, q, this, value
from napkin.program.canonical import program_bytes
from napkin.program.config import Configuration, ConfigurationError, InputValue, Numerics, Quantity, Request
from napkin.program.parts import Unit
from napkin.program.record import Curve, Key, Unavailable
from napkin.program.refs import THIS, Path

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def tank(*parts, request=None):
    """A tank of 8 L that a clinic drains at `request` (3 L/h unless given), with `parts` of its own."""
    b = Builder(UNITS)
    b.entity('tank', value('water', 'L', 8, lower=0, upper=20), *parts)
    b.entity('clinic', flow('delivery', named('tank').water, SINK, request=request or q(3, 'L/h')))
    return b.finish()


def at(record, program, path, *times):
    (found,) = read(record, program, [path], list(times))
    return list(found.values)


def test_call_builds_a_function_of_the_closed_list():
    """|water - 5 L| with water = 8 - 3t: 3 L at 0 h, 0 at 1 h, 1.5 L at 1.5 h."""
    program = tank(value('gap', 'L', formula(build.call('abs', this.water - q(5, 'L')))))
    record = run(program, Configuration(Request(2)))
    assert at(record, program, 'tank.gap', 0, 1, 1.5) == pytest.approx([3, 0, 1.5], abs=1e-12)


@pytest.mark.parametrize('name', ['abs', 'exp', 'expm1', 'ln', 'log1p', 'sqrt', 'erf', 'min', 'max', 'clip'])
def test_call_takes_each_function_of_the_language(name):
    arity = {'min': 2, 'max': 2, 'clip': 3}.get(name, 1)
    made = build.call(name, *([this.share] * arity))
    assert build.expr_of(made).node.function == name


@pytest.mark.parametrize('name', ['q', 'pow', 'round', 'since'])
def test_call_refuses_a_name_outside_the_closed_list(name):
    with pytest.raises(ValueError, match='no function of the language'):
        build.call(name, this.share)


@pytest.mark.parametrize('share, inside', [(0.5, True), (1, False), (0, True)])
def test_a_wrapped_node_is_a_chain_that_reads_its_value_once(share, inside):
    """`0 <= this.share < 1`, as `X(node, reads)` writes it: one chain of comparisons."""
    chain = X(
        nodes.compare(['le', 'lt'], [nodes.written(0), nodes.ref('share'), nodes.written(1)]),
        {'share': Path(THIS, ('share',))},
    )
    b = Builder(UNITS)
    b.entity('part', input_('share', '', share), value('inside', BOOL, formula(chain)))
    program = b.finish()
    assert at(run(program, Configuration(Request(1))), program, 'part.inside', 0) == [inside]


def test_a_flow_between_plain_numbers_has_its_rate_in_1_per_hour():
    """A count of 10 that drains 2 an hour: the builder gives the flow `1/h` from its ends (it gave
    `/h` before, which no table composed), and at 4 h the count is 10 - 8 = 2."""
    b = Builder(UNITS)
    b.entity('pool', value('count', '', 10, lower=0), flow('drain', this.count, SINK, request=2))
    program = b.finish()
    assert program.templates[0].flows[0].unit == '1/h'
    record = run(program, Configuration(Request(4)))
    rate, count = read(record, program, ['pool.drain.actual_rate', 'pool.count'], [4])
    assert (rate.unit, rate.values, count.values) == ('1/h', (2,), pytest.approx((2,)))


def test_the_builder_and_the_front_end_spell_a_plain_rate_alike():
    """The same pool from source and from the builder: one program, byte for byte."""
    text = (
        'scenario "Pool"\n    horizon 4 h\n\npool:\n    count = 10 in [0,]\n'
        '    flow drain: this.count -> SINK\n        request = formula(this.count / (5 h))\n'
    )
    lowered = compile_text(text, library_units(empty_library())).program
    b = Builder({'h': {'time': 1}})
    b.entity(
        'pool',
        value('count', '', 10, lower=0),
        flow('drain', this.count, SINK, request=formula(this.count / q(5, 'h'))),
    )
    assert program_bytes(b.finish()) == program_bytes(lowered)
    assert lowered.templates[0].flows[0].unit == '1/h'


def test_a_curved_piece_is_read_from_its_own_series():
    """A drain at water / 2 h: water = 8 exp(-t / 2). The record's curved pieces hold a `Curve` and
    no rate, and the program's own reader (`History.at`) follows the exponential."""
    program = tank(request=formula(named('tank').water / q(2, 'h')))
    record = run(program, Configuration(Request(4)))
    history = record.history(Key('tank', ('water',)))
    curved = [piece for piece in history.pieces if piece.curve is not None]
    assert curved
    assert all(isinstance(piece.curve, Curve) and piece.rate == 0 for piece in curved)
    for t in (0.3, 1.7, 2.25, 4):
        assert history.at(t) == pytest.approx(8 * math.exp(-t / 2), rel=1e-9)


def test_a_curve_reads_the_increase_of_its_chebyshev_series():
    """T0 + T1 + T3 over 4 h, at 3 h: u = 0.5, and the series rises from 1 - 1 - 1 = -1 at u = -1 to
    1 + 0.5 + (4 (0.5)^3 - 3 (0.5)) = 0.5, by 1.5."""
    assert Curve(4.0, (1.0, 1.0, 0.0, 1.0)).increase(3.0) == pytest.approx(1.5, abs=1e-15)


def test_an_input_in_a_unit_of_the_library_that_the_program_does_not_spell():
    """2 days for a repair time in hours: 48 h. A unit of volume does not convert."""
    b = Builder(UNITS)
    b.entity('machine', input_('repair_time', 'h', 1, lower=0, upper=100))
    program = b.finish()
    day = Unit('day', (('time', 1),), Fraction(24))
    given = Configuration(Request(1), inputs=(InputValue('machine', 'repair_time', Quantity(2, day)),))
    assert at(run(program, given), program, 'machine.repair_time', 0) == pytest.approx([48])
    litre = Unit('litre', (('volume', 1),), Fraction(1))
    wrong = Configuration(Request(1), inputs=(InputValue('machine', 'repair_time', Quantity(2, litre)),))
    with pytest.raises(ConfigurationError, match='litre does not convert'):
        run(program, wrong)


def low_at(crossing):
    """The time at which the record of `water <= 5.5 L` changes to true: water = 8 - 3t reaches
    the comparison band just before 5/6 h; the record locates its entry within `crossing`."""
    program = tank(value('low', BOOL, formula(this.water <= q(Fraction(11, 2), 'L'))))
    record = run(program, Configuration(Request(2), numerics=Numerics(crossing=crossing)))
    pieces = record.history(Key('tank', ('low',))).pieces
    assert [piece.value for piece in pieces] == [False, True]
    return pieces[1].t


def test_the_engine_locates_a_change_to_the_crossing_tolerance_of_the_configuration():
    """The fit of a yes/no checks it at Chebyshev points of [0, 2] h, 0.826 h and 1.174 h about
    5/6 h, and halves that bracket while it is wider than the tolerance: once for 0.25 h, at 1 h."""
    band_entry = (8 - 5.5 / (1 - Numerics().rtol)) / 3  # water - 5.5 = rtol × water
    assert band_entry <= low_at(1e-8) <= band_entry + 1e-8
    assert low_at(0.25) == pytest.approx(1, abs=1e-12)


def test_a_solver_is_stalled_by_steps_shorter_than_its_moment():
    """Steps of 0.25 h are shorter than a moment of 0.5 h: STALLED_STEPS of them stall the solver.
    With the default moment of a configuration they never do."""
    coarse, default = Limit(1.0, 8.0, moment=0.5), Limit(1.0, 8.0)
    t = 0.0
    for _ in range(STALLED_STEPS - 1):
        assert not coarse.accepted(t, t + 0.25)
        assert not default.accepted(t, t + 0.25)
        t += 0.25
    assert coarse.accepted(t, t + 0.25)
    assert not default.accepted(t, t + 0.25)


def test_a_record_of_some_values_keeps_what_their_formulas_read():
    """Only `tank.low` is asked for; the record keeps `tank.water` too, and `read` evaluates the
    formula from it: false before 1 h, true after."""
    program = tank(value('low', BOOL, formula(this.water <= q(5, 'L'))))
    keys = (Key('tank', ('low',)),)
    record = run(program, Configuration(Request(2, everything=False, keys=keys)))
    assert {history.key for history in record.histories} == {Key('tank', ('low',)), Key('tank', ('water',))}
    assert at(record, program, 'tank.low', 0.5, 1.5) == [False, True]
    ((unheld,),) = (found.values for found in read(record, program, ['tank.water'], [1]))
    assert isinstance(unheld, Unavailable) and unheld.reason.startswith(
        'the record holds no value of tank.water'
    )
