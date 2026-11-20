"""A store bound within the time tolerance of a scheduled stage reaches it in that moment.

The incoming pipe still delivers 1 L/h in the opening round. A full tank closes the pipe on
re-share. An edit withdrawing water at a stop takes precedence over the arriving upper bound.
"""

import math
from fractions import Fraction

import pytest

from napkin.engine import read
from napkin.engine.report import report
from napkin.engine.timeline import Plan, Run
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    after,
    assign,
    constraint,
    endpoint,
    event,
    flow,
    formula,
    given,
    ifelse,
    local,
    maximize,
    named,
    q,
    solve_for,
    solver,
    start,
    this,
    value,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.config import Configuration, Numerics, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


WAYS = ['family', 'lines', 'component', 'sparse', 'declared', 'moving']


def fill(gap, way='family'):
    upper = 1 + gap
    builder = Builder(UNITS)
    if way in ('sparse', 'component'):
        amount = formula(ifelse(this.water < q(8, 'L'), q(1, 'L/h'), q(2, 'L/h')))
    else:
        amount = q(4 if way in ('declared', 'moving') else 1, 'L/h')
    settings = {'inflow': endpoint(capacity=q(10, 'L/h'))} if way == 'sparse' else {}
    pipes = [flow('fill', SOURCE, this.water, request=amount)]
    if way == 'lines':
        pipes.append(flow('extra', this.water, SINK, request=q(0, 'L/h'), capacity=q(0, 'L/h')))
    tank = builder.entity('tank', value('water', 'L', 0, lower=0, upper=upper, **settings), *pipes)
    if way in ('declared', 'moving'):
        limits = [constraint(local.use.actual_rate <= q(1, 'L/h'))]
        if way == 'moving':
            limits.append(
                constraint(local.use.actual_rate <= ifelse(local.water < q(8, 'L'), q(1, 'L/h'), q(2, 'L/h')))
            )
        builder.entity(
            'provider',
            solver(
                'share',
                given('use', tank.fill),
                given('water', tank.water),
                solve_for(local.use.actual_rate),
                *limits,
                maximize(local.use.actual_rate),
            ),
        )
    builder.entity('gauge', value('water', 'L', 0), flow('fill', SOURCE, this.water, request=q(3, 'L/h')))
    builder.entity(
        'reader',
        value('level', 'L', -1),
        value('incoming', 'L/h', -1),
        value('shared', 'L/h', -1),
        event(
            'look',
            after(q(1, 'h'), assign(this.level, tank.water), assign(this.incoming, tank.fill.actual_rate)),
            after(q(0, 'h'), assign(this.shared, tank.fill.actual_rate)),
        ),
    )
    builder.setup(start(named('reader').look))
    return builder.finish()


@pytest.mark.parametrize('fraction', [-2, -0.5, 0, 0.5, 2])
@pytest.mark.parametrize('way', WAYS)
def test_a_bound_on_either_side_of_a_scheduled_stage(fraction, way):
    tolerance = Numerics().crossing
    gap = fraction * tolerance
    program, config = fill(gap, way), Configuration(Request(2))
    made = Run(Plan.of(program, config))
    record = made.run()
    connected = made.ways.sets[made.ways.set_of['tank.water']][0]
    assert ('moving' if connected.way == 'declared' and connected.moves else connected.way) == way
    assert record.failure is None
    grouped = abs(fraction) <= 1
    observed = [
        r.values[0] for r in read(record, program, ['reader.level', 'reader.incoming', 'reader.shared'], [1])
    ]
    direct = 1 + gap if fraction <= 1 else 1
    if grouped:
        assert observed[0] == direct
    else:
        assert observed[0] == pytest.approx(direct, abs=config.numerics.atol_factor, rel=0)
    assert observed[1:] == [float(fraction >= -1), float(fraction > 1)]
    # This gauge is independent of the grouped bound. It follows its exact line on every path.
    oracle, failure = run_of(program, config)
    assert failure is None
    key = Key('gauge', ('water',))
    for at, observed_gauge in zip((1, 2), read(record, program, [key], [1, 2])[0].values, strict=True):
        assert observed_gauge == value_at(oracle, program, key, Fraction(at)) == 3 * at
    ties = record.entries('contact')
    assert len(ties) == int(grouped)
    if grouped:
        (entry,) = ties
        assert (entry.t, entry.round, entry.part, entry.owner) == (1, 1, 'tank.water', 'tank')
        located = entry.detail('located')
        assert abs(located - (1 + gap)) <= tolerance
        ((_, _, difference, band),) = entry.detail('near')
        assert (difference, band) == (located - 1, tolerance)
        (tie,) = report(record, program, config, ['gauge.water'], [1]).near_ties
        assert tie.difference == difference and tie.tolerance == band
        assert f'difference {difference:+.3g} h, tolerance {band:.3g} h' in tie.message


@pytest.mark.parametrize('way', WAYS)
def test_a_bound_grouped_with_an_edit_keeps_the_edit_and_timing_entry(way):
    program, config = fill(Numerics().crossing / 2, way), Configuration(Request(2))
    made = Run(Plan.of(program, config), (Breakpoint('reader.look.step[0]'),))
    stop = made.run()
    assert isinstance(stop, Checkpoint)
    assert made.arriving  # the paused round still owns the incoming segment
    assert stop.state.value('tank.water') == 1 + Numerics().crossing / 2
    edited = made.edit(Key('tank', ('water',)), 0.25)
    restored = Run.restored(Plan.of(program, config), loads(dumps(edited)))
    assert restored.arriving
    for record in (made.resume(), restored.resume()):
        assert record.failure is None
        answers = read(record, program, ['reader.level', 'reader.incoming', 'reader.shared'], [1])
        assert [r.values[0] for r in answers] == [0.25, 1, 1]
        (entry,) = record.entries('contact')
        assert entry.t == 1 and entry.part == 'tank.water'


@pytest.mark.parametrize('direction', [-1, 1])
def test_the_closed_ends_of_the_timing_window_report_an_exact_line_contact(direction):
    config = Configuration(Request(2))
    gap = direction * config.numerics.crossing
    edge = 1 + gap
    record = Run(Plan.of(fill(gap), config)).run()
    (entry,) = record.entries('contact')
    assert (entry.t, entry.detail('located')) == (1, edge)
    made = Run(Plan.of(fill(gap), config))
    assert made.clock.within(edge, 1)
    assert not made.clock.within(math.nextafter(edge, direction * math.inf), 1)
