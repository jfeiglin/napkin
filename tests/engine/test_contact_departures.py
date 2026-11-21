"""An opening stage reads the incoming rates. After its re-share, every engine leaves a
consumed contact on the same side, including when a checkpoint edit changed the rates."""

import math
from fractions import Fraction as F

import pytest

from napkin.engine import read
from napkin.engine.timeline import Plan, Run
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    after,
    assign,
    endpoint,
    event,
    flow,
    formula,
    given,
    ifelse,
    local,
    named,
    q,
    solve_for,
    solver,
    start,
    t,
    this,
    value,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.engine.test_grouped_contacts import UNITS, fill


def reversal(at, way, simultaneous):
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 1, lower=0, outflow=endpoint(capacity=q(10, 'L/h')) if way == 'sparse' else None),
        value('high', 'L/h', 1),
        value('incoming', 'L/h', 0),
        value('shared', 'L/h', 0),
        flow('fill', SOURCE, this.water, request=formula(ifelse(t <= q(1, 'h'), q(2, 'L/h'), q(0, 'L/h')))),
        flow(
            'drain',
            this.water,
            SINK,
            request=formula(
                ifelse(this.water < q(2, 'L'), this.high, q(F(1, 2), 'L/h')) if simultaneous else this.high
            ),
        ),
        event(
            'look',
            after(q(at, 'h'), assign(this.incoming, this.fill.actual_rate)),
            after(q(0, 'h'), assign(this.shared, this.drain.actual_rate)),
        ),
    )
    if way == 'moving':
        b.entity(
            'provider',
            solver(
                'dispatch',
                given('fill', tank.fill),
                given('drain', tank.drain),
                solve_for(local.fill.actual_rate),
                solve_for(local.drain.actual_rate),
            ),
        )
    b.setup(start(named('tank').look))
    return b.finish()


@pytest.mark.parametrize('case', ['switch', 'bound', 'coincidence'])
@pytest.mark.parametrize(
    'gap',
    [
        0,
        pytest.param(F(-1, 10**10), marks=pytest.mark.deep),
        pytest.param(F(1, 10**10), marks=pytest.mark.deep),
    ],
)
@pytest.mark.parametrize('path', ['straight', 'edited', 'restored'])
def test_consumed_contacts_have_the_same_departure_in_each_engine(case, gap, path):
    """At 1 h the fill switches off after raising the level from 1 to 2 L. With no fill,
    the lower-side drain takes 1 L/h (1.5 after editing high). The separate bound model fills
    1 L/h up to its cap. Withdrawing all but 1/4 L at the stop reopens its pipe."""
    bound = case == 'bound'
    simultaneous = case == 'coincidence'
    at = F(1) if bound else 1 + gap
    horizon = at + F(1, 4)
    ways = ['component', 'sparse', 'moving'] + (['lines', 'family', 'declared'] if bound else [])
    for way in ways:
        program = fill(float(gap), way) if bound else reversal(at, way, simultaneous)
        config = Configuration(Request(float(horizon)))
        who = 'reader' if bound else 'tank'
        work = Run(
            Plan.of(program, config), () if path == 'straight' else (Breakpoint(f'{who}.look.step[0]'),)
        )
        record = work.run()
        if path != 'straight':
            assert isinstance(record, Checkpoint)
            edited = work.edit(Key('tank', ('water' if bound else 'high',)), 0.25 if bound else 1.5)
            if path == 'restored':
                work = Run.restored(Plan.of(program, config), loads(dumps(edited)))
            record = work.resume()
        connected = work.ways.sets[work.ways.set_of['tank.water']][0]
        assert ('moving' if connected.way == 'declared' and connected.moves else connected.way) == way
        assert record.failure is None, (case, way, path, record.failure)
        contacts = record.entries('contact')
        assert len(contacts) == (2 if simultaneous else 1), (way, contacts)
        raw = float(1 + gap) if bound else 1
        parts = ['tank.water'] if bound else ['tank.drain', 'tank.fill'] if simultaneous else ['tank.fill']
        assert sorted(e.part for e in contacts) == parts
        for e in contacts:
            assert (e.t, e.round, e.owner) == (float(at), 1, 'tank')
            assert e.detail('located') == pytest.approx(raw, abs=1e-12, rel=0)
            ((name, comparison, delta, tolerance),) = e.detail('near')
            kind = 'upper bound' if bound else 'switch'
            assert (name, comparison, tolerance) == (
                e.part,
                f'{kind} of {e.part} and the moment at {float(at):g} h',
                config.numerics.crossing,
            )
            assert delta == e.detail('located') - e.t
            assert delta == pytest.approx(raw - float(at), abs=1e-12, rel=0)
        if bound:
            # A hard 1 L/h upper rate leaves the positive in-band remainder on the books.
            level = 1 if gap > 0 and way in ('declared', 'moving') else float(1 + gap)
            expected = [1, 0, level] if path == 'straight' else [1, 1, 0.5]
        else:
            drain = 1 if path == 'straight' else F(3, 2)
            # A single located stock threshold is exact at the canonical moment. Without it,
            # the incoming rate moves the stock to the stage's authored time.
            level = 2 if simultaneous else 1 + at
            expected = [2, drain, level - drain / 4]
        if bound or simultaneous:
            anchored = 2 if simultaneous else (level if path == 'straight' else 0.25)
            observed = read(record, program, ['tank.water'], [float(at)])[0].values
            if bound and path == 'straight' and gap > 0 and way in ('declared', 'moving'):
                assert observed == pytest.approx((anchored,), rel=0, abs=8 * math.ulp(1))
                assert observed == read(record, program, ['reader.level'], [float(at)])[0].values
            else:
                assert observed == (anchored,)
        rows = read(record, program, [f'{who}.incoming', f'{who}.shared', 'tank.water'], [float(horizon)])
        incoming, outgoing, stock = (r.values[0] for r in rows)
        assert (incoming, outgoing) == tuple(expected[:2]), (way, path)
        answer = float(expected[2])
        assert abs(stock - answer) <= 8 * math.ulp(answer), (way, path, stock, answer)
