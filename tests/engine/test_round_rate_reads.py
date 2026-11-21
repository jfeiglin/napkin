"""Stages read the rates of the last sharing at their time (PLAN, change 27).

Each small model copies one rate in the changing stage, a later stage of the round, after zero
hours and one hour later. The answers come from the requests and limits below. A second pipe
makes an edit at a stop visible in the next round. The interpreter and both ways of resuming the
engine must give each answer. Cases with a firing pass the rate as an argument as well.
"""

import random
from fractions import Fraction as F

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run, resume
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    after,
    assign,
    endpoint,
    event,
    flow,
    fmin,
    formula,
    ifelse,
    input_,
    legs,
    local,
    move,
    named,
    param,
    priority,
    q,
    reset_when,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.engine.test_solvers import UNITS, staffing
from tests.reference.from_program import run_of, value_at

STOP = 'ops.change.step[0]'
SETTING = Key('tap', ('setting',))
KINDS = (
    'request',
    'capacity',
    'allocation',
    'store',
    'move',
    'join',
    'leave',
    'fire',
    'key',
    'switch',
    'time',
    'moving store',
    'legs',
)


def rate(number):
    return q(number, 'L/h')


def key(path):
    owner, *steps = path.split('.')
    return Key(owner, tuple(steps))


def check(program, horizon, expected, stop=None, origin=STOP):
    """Check every named observation against its hand-worked answer on both runtimes."""
    configuration = Configuration(Request(horizon))
    stops = [(origin, None, [stop])] if stop else []
    oracle, failure = run_of(program, configuration, stops)
    if stop:
        made = Run(Plan.of(program, configuration), (Breakpoint(origin),))
        paused = made.run()
        assert isinstance(paused, Checkpoint), paused
        edited = made.edit(*stop)
        records = (made.resume(), resume(program, loads(dumps(edited))))
    else:
        records = (run(program, configuration),)
    assert [failure, *(rec.failure for rec in records)] == [None] * (len(records) + 1)
    for path, at, answer in expected:
        target = key(path)
        assert value_at(oracle, program, target, F(at)) == answer, (path, at)
        for rec in records:
            (found,) = read(rec, program, [target], [at])[0].values
            assert found == pytest.approx(float(answer), abs=1e-8), (path, at)


def model(kind, seed, *, mixed_amounts=False):
    """One store of water and two claims on its outflow, with one change at 2 h."""
    rng = random.Random(seed)
    a, b = rng.randint(2, 5), rng.randint(1, 3)
    tank, ops, tap = named('tank'), named('ops'), named('tap')
    builder = Builder(UNITS)
    builder.entity(
        'tap',
        value('setting', 'L/h', b),
        flow('pipe', SOURCE, SINK, request=formula(this.setting), unit='L/h'),
    )
    unit, picked = 'L/h', tank.main.actual_rate
    capacity, request = a + b, rate(a)
    claims = [flow('garden', this.water, SINK, request=rate(b))]
    changes, parts, setup = [], [], []
    peer_reads, next_reads, extra_answers = [], [], []
    before, shared = a, a
    if kind == 'request':
        changes.append(assign(tank.garden.request, rate(2 * b)))
        shared = F(a * (a + b), a + 2 * b)
    elif kind in ('capacity', 'allocation'):
        capacity = a
        before = F(a * a, a + b)
        if kind == 'capacity':
            changes.append(assign(tank.water.outflow.capacity, rate(a + b)))
        else:
            changes.append(assign(tank.water.outflow.allocation, priority(tank.main)))
    elif kind in ('store', 'move'):
        builder.entity('stock', value('level', 'L', a, lower=0), value('bucket', 'L', 0, lower=0))
        stock = named('stock')
        if mixed_amounts:
            # Deposit in a large inventory, remove the principal, then pay back the deposits.
            rng = random.Random(seed + 0x8E422DA)
            bulk = 10 ** rng.randint(3, 7)
            deposit = F(rng.choice((1, 3, 7, 50)), 1000)
            count = rng.randint(2, 12)
            bank = builder.entity(
                'bank',
                value('principal', 'L', bulk, lower=0),
                value('deposits', 'L', float(count * deposit), lower=0),
            )
            changes.extend(
                [
                    move(q(bulk, 'L'), bank.principal, stock.level),
                    *(move(q(deposit, 'L'), bank.deposits, stock.level) for _ in range(count)),
                    move(q(bulk, 'L'), stock.level, bank.principal),
                    move(q(count * deposit, 'L'), stock.level, bank.deposits),
                ]
            )
            extra_answers.extend(
                (
                    ('bank.principal', 2, bulk),
                    ('bank.deposits', 2, count * deposit),
                    ('stock.level', 2, 0),
                    ('stock.bucket', 2, a),
                )
            )
        request = formula(stock.level * q(1, '1/h'))
        changes.append(
            assign(stock.level, q(0, 'L')) if kind == 'store' else move(q(a, 'L'), stock.level, stock.bucket)
        )
        shared = 0
    elif kind in ('join', 'leave', 'fire'):
        # The occurrence makes a second claim of b on the outlet's a units.
        capacity, claims = a, []
        triggers = []
        if kind == 'fire':
            triggers = [when(t >= q(2, 'h'), start(this.deliver), reset=reset_when(False))]
            parts.extend(
                (
                    event(
                        'note',
                        param('got', 'L/h'),
                        after(q(0, 'h'), assign(ops.noted, local.got)),
                        when(t >= q(2, 'h'), start(this.note, picked), reset=reset_when(False)),
                    ),
                    value('noted', 'L/h', -1),
                )
            )
        parts.insert(
            0,
            event(
                'deliver',
                flow('pipe', tank.water, SINK, request=rate(b)),
                flow('tap', SOURCE, SINK, request=rate(b), unit='L/h'),
                after(q(2, 'h')),
                *triggers,
            ),
        )
        together = F(a * a, a + b)
        if kind == 'leave':
            setup.append(start(ops.deliver))
            before = together
        else:
            shared = together
            if kind == 'join':
                changes.append(start(ops.deliver))
        if kind != 'fire':
            delivery = ops.deliver.occurrences.at(t)
            parts.extend(
                value(name, 'L/h', -1) for name in ('member', 'member_next', 'outside', 'outside_next')
            )
            peer_reads.extend(
                (assign(ops.member, delivery.pipe.actual_rate), assign(ops.outside, delivery.tap.actual_rate))
            )
            next_reads.extend(
                (
                    assign(ops.member_next, delivery.pipe.actual_rate),
                    assign(ops.outside_next, delivery.tap.actual_rate),
                )
            )
            member_share = F(a * b, a + b)
            extra_answers.extend(
                (
                    ('ops.member', 2, member_share if kind == 'leave' else 0),
                    ('ops.member_next', 2, 0 if kind == 'leave' else member_share),
                    ('ops.outside', 2, b if kind == 'leave' else 0),
                    ('ops.outside_next', 2, 0 if kind == 'leave' else b),
                )
            )
    elif kind == 'time':
        # This pipe is unrestricted so its rate at 2 h is exactly twice its slope.
        builder.entity(
            'clock',
            value('volume', 'L', 0, lower=0),
            flow('feed', SOURCE, this.volume, request=formula(t * q(a, 'L/h/h'))),
        )
        picked = named('clock').feed.actual_rate
        changes.append(assign(named('clock').feed.request, rate(b)))
        before, shared = 2 * a, b
    elif kind == 'moving store':
        # The gauge's water increases by 1 L each hour, including the hour after the write.
        gauge = named('gauge')
        builder.entity(
            'gauge',
            value('water', 'L', a, lower=0),
            flow('fill', SOURCE, this.water, request=rate(1)),
            flow('meter', SOURCE, SINK, unit='L/h', request=formula(this.water * q(1, '1/h'))),
        )
        picked = gauge.meter.actual_rate
        changes.append(assign(gauge.water, q(b, 'L')))
        before, shared = a + 2, b
    elif kind in ('key', 'switch'):
        if kind == 'key':
            rows = builder.template('Reading', input_('hour', 'h', 0), input_('factor', '', 1))
            builder.table('readings', rows, ({'hour': 0, 'factor': a}, {'hour': 2, 'factor': 1}))
            request = formula(rows.instances.by('hour').at(t).factor * rate(1))
        else:
            request = formula(ifelse(t < q(2, 'h'), rate(a), rate(1)))
        shared = 1
    else:
        # Doubling the first leg's request halves the fraction served at the limited outlet.
        claims = [
            legs(
                'pair',
                flow('one', this.water, SINK, request=rate(a)),
                flow('two', SOURCE, this.received, request=rate(b)),
            )
        ]
        capacity, request = a, rate(0)
        changes.extend(
            (assign(tank.pair.one.request, rate(2 * a)), assign(ops.leg, tank.pair.one.actual_rate))
        )
        parts.extend(
            (
                value('leg', 'L/h', -1),
                value('incoming', 'L/h', formula(tank.received.inflow.actual_rate)),
                value('endpoint', 'L/h', -1),
                value('endpoint_next', 'L/h', -1),
            )
        )
        peer_reads.append(assign(ops.endpoint, ops.incoming))
        next_reads.append(assign(ops.endpoint_next, ops.incoming))
        extra_answers.extend((('ops.leg', 2, a), ('ops.endpoint', 2, b), ('ops.endpoint_next', 2, F(b, 2))))
        if seed % 2:
            unit, picked, before, shared = '', tank.pair.served_fraction, 1, F(1, 2)
        else:
            picked, before, shared = tank.pair.two.actual_rate, b, F(b, 2)
    builder.entity(
        'tank',
        value('water', 'L', 100, lower=0, outflow=endpoint(capacity=rate(capacity))),
        value('received', 'L', 0, lower=0),
        flow('main', this.water, SINK, request=request),
        *claims,
    )
    builder.entity(
        'ops',
        value('same', unit, -1),
        value('peer', unit, -1),
        value('next', unit, -1),
        value('later', unit, -1),
        value('mixed', 'L/h', formula(tap.pipe.actual_rate + tap.setting)),
        value('copy', 'L/h', -1),
        value('tap_after', 'L/h', -1),
        *parts,
        event('change', after(q(2, 'h'), *changes, assign(this.same, picked), assign(this.copy, this.mixed))),
        event(
            'look',
            after(q(2, 'h'), assign(this.peer, picked), *peer_reads),
            after(
                q(0, 'h'),
                assign(this.next, picked),
                assign(this.tap_after, tap.pipe.actual_rate),
                *next_reads,
            ),
            after(q(1, 'h'), assign(this.later, picked)),
        ),
    )
    builder.setup(*setup, start(ops.change), start(ops.look))
    expected = [
        *extra_answers,
        ('ops.same', 2, before),
        ('ops.peer', 2, before),
        ('ops.next', 2, before if kind == 'fire' else shared),
        ('ops.later', 3, shared + 1 if kind == 'moving store' else shared),
    ]
    if kind == 'fire':
        expected.append(('ops.noted', 2, before))
    return builder.finish(), expected, b


def compare(kind, seed):
    program, observations, initial = model(kind, seed)
    for edit in (None, (SETTING, initial + 1)):
        setting = initial if edit is None else edit[1]
        expected = [*observations, ('ops.copy', 2, initial + setting), ('ops.tap_after', 2, setting)]
        check(program, 3, expected, edit)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('seed', [0, 1])
def test_stages_and_firings_read_the_rates_of_their_round(kind, seed):
    compare(kind, seed)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(2, 46))
def test_more_rounds_with_writes_and_changes_of_their_own(seed):
    compare(KINDS[seed % len(KINDS)], seed)


def test_clinic_and_garden_share_again_after_the_stages():
    builder = Builder(UNITS)
    builder.entity(
        'tank',
        value('water', 'L', 100, lower=0, outflow=endpoint(capacity=rate(6))),
        flow('clinic', this.water, SINK, request=rate(4)),
        flow('garden', this.water, SINK, request=rate(2)),
        value('same', 'L/h', -1),
        value('next', 'L/h', -1),
        event(
            'raise_garden',
            after(
                q(2, 'h'), assign(this.garden.request, rate(6)), assign(this.same, this.clinic.actual_rate)
            ),
            after(q(0, 'h'), assign(this.next, this.clinic.actual_rate)),
        ),
    )
    builder.setup(start(named('tank').raise_garden))
    check(
        builder.finish(),
        3,
        [
            ('tank.same', 2, 4),
            ('tank.next', 2, F(12, 5)),
            ('tank.clinic.actual_rate', 1, 4),
            ('tank.clinic.actual_rate', 2, F(12, 5)),
            ('tank.clinic.actual_rate', 3, F(12, 5)),
        ],
    )


def test_the_next_staffing_delay_uses_56_hours():
    builder = Builder(UNITS)
    builder.entity(
        'office',
        value('staff_hours', 'h', 100),
        value('outreach_minimum', 'h', formula(F(3, 10) * this.staff_hours)),
        staffing(),
        value('same', 'h', -1),
        value('done', 'h', -1),
        event(
            'cut',
            after(q(1, 'h'), assign(this.staff_hours, q(80, 'h')), assign(this.same, this.staffing.care)),
            after(this.staffing.care, assign(this.done, t)),
        ),
    )
    builder.setup(start(named('office').cut))
    check(
        builder.finish(),
        58,
        [
            ('office.same', 1, 70),
            ('office.staffing.care', 1, 56),
            ('office.done', 56, -1),
            ('office.done', 57, 57),
        ],
    )


def test_an_endpoint_rate_in_setup_still_stops_by_name():
    """The initial sharing is after setup. Even an outlet with a pipe has no shared rate yet."""
    builder = Builder(UNITS)
    builder.entity(
        'tank',
        value('water', 'L', 8, lower=0),
        flow('pipe', this.water, SINK, request=rate(3)),
        value('seen', 'L/h', -1),
    )
    tank = named('tank')
    builder.setup(assign(tank.seen, tank.water.outflow.actual_rate))
    program = builder.finish()
    configuration = Configuration(Request(1))
    oracle, failed = run_of(program, configuration)
    record = run(program, configuration)
    # The old calculation names the pipe that supplies this endpoint's rate.
    names = ('tank.water.outflow.actual_rate', 'tank.pipe.actual_rate')
    assert failed is not None and any(name in str(failed) for name in names)
    assert oracle is None or oracle.view.t == 0
    assert record.failure is not None and record.failure.t == 0
    assert any(name in record.failure.detail('message') for name in names)


@pytest.mark.parametrize(
    'kind', ['time <', 'time <=', 'store <', 'store <=', 'two stores <', 'two stores <=', 'key']
)
def test_an_outside_pipe_reads_the_incoming_side_of_a_switch_or_key(kind):
    """An outside pipe delivers 4 L/h before the switch at 2 h and 1 L/h from it on."""
    builder = Builder(UNITS)
    if kind == 'key':
        rows = builder.template('Reading', input_('hour', 'h', 0), input_('factor', '', 1))
        builder.table('readings', rows, ({'hour': 0, 'factor': 4}, {'hour': 2, 'factor': 1}))
        request = formula(rows.instances.by('hour').at(t).factor * rate(1))
    else:
        if kind.startswith('two stores'):
            # 98 + 2t and 100 + t reach 102 L together at 2 h. The first then overtakes the second.
            for name, initial, fill in [('fast', 98, 2), ('slow', 100, 1)]:
                builder.entity(
                    name,
                    value('level', 'L', initial, lower=0),
                    value('setting', 'L/h', fill),
                    flow('fill', SOURCE, this.level, request=formula(this.setting)),
                )
            reading, threshold = named('fast').level, named('slow').level
        elif kind.startswith('store'):
            builder.entity(
                'gauge', value('level', 'L', 100, lower=0), flow('fill', SOURCE, this.level, request=rate(1))
            )
            reading, threshold = named('gauge').level, q(102, 'L')
        else:
            reading, threshold = t, q(2, 'h')
        before = reading <= threshold if kind.endswith('<=') else reading < threshold
        request = formula(ifelse(before, rate(4), rate(1)))
    builder.entity(
        'tap',
        flow('pipe', SOURCE, SINK, request=request, unit='L/h'),
        value('before', 'L/h', -1),
        value('afterward', 'L/h', -1),
        event(
            'copy',
            after(q(2, 'h'), assign(this.before, this.pipe.actual_rate)),
            after(q(0, 'h'), assign(this.afterward, this.pipe.actual_rate)),
        ),
    )
    builder.setup(start(named('tap').copy))
    program = builder.finish()
    expected = [
        ('tap.before', 2, 4),
        ('tap.afterward', 2, 1),
        ('tap.pipe.actual_rate', 1, 4),
        ('tap.pipe.actual_rate', 2, 1),
        ('tap.pipe.actual_rate', 3, 1),
    ]
    check(program, 3, expected)
    if kind.startswith('two stores'):
        # Halving the slow fill at the stop leaves the crossing in place and gives 102½ L at 3 h.
        check(
            program,
            3,
            [*expected, ('slow.level', 3, F(205, 2))],
            (key('slow.setting'), 0.5),
            origin='tap.copy.step[0]',
        )


@pytest.mark.parametrize('source', ['clock', 'table'])
@pytest.mark.parametrize(('at', 'following'), [(F(2), 0), (F(2) - F(1, 100000), 3)])
def test_the_rate_shared_when_a_switched_fill_meets_its_bound(at, following, source):
    """2 + 5 × 1 + 3 × 1 = 10 L at 2 h. Just before that time the 3 L/h still fits."""
    builder = Builder(UNITS)
    builder.entity('tank', value('water', 'L', 2, lower=0, upper=10))
    water = named('tank').water
    if source == 'clock':
        request = formula(fmin(rate(3), ifelse(t >= q(1, 'h'), rate(1), rate(3))))
    else:
        rows = builder.template('Reading', input_('hour', 'h', 0), input_('factor', '', 1))
        builder.table('readings', rows, ({'hour': 0, 'factor': 3}, {'hour': 1, 'factor': 1}))
        request = formula(rows.instances.by('hour').at(t).factor * rate(1))
    builder.entity('pipe', flow('fill', SOURCE, water, request=request))
    builder.entity('pump', flow('fill', SOURCE, water, request=rate(2)))
    builder.entity(
        'ops',
        value('before', 'L/h', -1),
        value('afterward', 'L/h', -1),
        event(
            'look',
            after(q(at, 'h'), assign(this.before, water.inflow.actual_rate)),
            after(q(0, 'h'), assign(this.afterward, water.inflow.actual_rate)),
        ),
    )
    builder.setup(start(named('ops').look))
    check(
        builder.finish(),
        3,
        [
            ('ops.before', at, 3),
            ('ops.afterward', at, following),
            ('tank.water.inflow.actual_rate', at, following),
        ],
    )


def test_a_new_request_formula_changes_the_rate_after_this_round():
    """At 2 h the first pipe is carrying 1 + 2 L/h. Its new request is 1 L/h."""
    builder = Builder(UNITS)
    builder.entity(
        'tank',
        value('water', 'L', 100, lower=0),
        flow('first', this.water, SINK, request=formula(rate(1) + t * q(1, 'L/h/h'))),
        flow('second', this.water, SINK, request=rate(3)),
        value('before', 'L/h', -1),
        value('afterward', 'L/h', -1),
        event('cut', after(q(2, 'h')), after(q(0, 'h'), assign(this.first.request, formula(rate(1))))),
        event(
            'copy',
            after(q(2, 'h')),
            after(q(0, 'h'), assign(this.before, this.first.actual_rate)),
            after(q(0, 'h'), assign(this.afterward, this.first.actual_rate)),
        ),
    )
    tank = named('tank')
    builder.setup(start(tank.cut), start(tank.copy))
    program = builder.finish()
    expected = [('tank.before', 2, 3), ('tank.afterward', 2, 1)]
    check(program, 3, expected)
    check(program, 3, expected, (Key('tank', ('water',)), 60), origin='tank.copy.step[1]')


@pytest.mark.parametrize('filling', [False, True], ids=['empty', 'full'])
@pytest.mark.parametrize(('first', 'amount', 'contact'), [(2, 2, 1), (3, 8, 3)])
@pytest.mark.parametrize('early', [False, True])
def test_a_firing_reads_the_sharing_at_a_tanks_bound(first, amount, contact, early, filling):
    """Moving 2 L takes 1 h at 2 L/h. Moving 8 L takes 3 h at 3 L/h for 2 h and 2 L/h after."""
    builder = Builder(UNITS)
    at = F(contact) - (F(1, 100000) if early else 0)
    source, sink = (SOURCE, this.water) if filling else (this.water, SINK)
    builder.entity(
        'tank',
        value('water', 'L', 10 - amount if filling else amount, lower=0, upper=10),
        flow('pipe', source, sink, request=formula(ifelse(t < q(2, 'h'), rate(first), rate(2)))),
    )
    pipe = named('tank').pipe
    builder.entity(
        'ops',
        value('noted', 'L/h', -1),
        event(
            'note',
            param('got', 'L/h'),
            when(t >= q(at, 'h'), start(this.note, pipe.actual_rate), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.noted, local.got)),
        ),
    )
    check(builder.finish(), 4, [('ops.noted', at, 2 if early else 0)])


@pytest.mark.parametrize('inclusive', [False, True])
def test_an_outside_clock_switch_without_a_stage_has_its_own_rate_history(inclusive):
    b = Builder(UNITS)
    before = t <= q(2, 'h') if inclusive else t < q(2, 'h')
    b.entity('tap', flow('pipe', SOURCE, SINK, unit='L/h', request=formula(ifelse(before, rate(4), rate(1)))))
    program = b.finish()
    record = run(program, Configuration(Request(4)))
    rate_key = key('tap.pipe.actual_rate')
    assert record.failure is None and not record.entries('contact')
    assert tuple(record.value(rate_key, at) for at in (1, 2, 3)) == pytest.approx((4, 1, 1))
    assert read(record, program, [rate_key], [1, 2, 3])[0].values == pytest.approx((4, 1, 1))


@pytest.mark.parametrize('distance', [F(-1, 200000000), F(1, 200000000)])
def test_an_outside_switch_within_rounding_of_a_stage_uses_that_moment(distance):
    at = F(2) + distance
    b = Builder(UNITS)
    b.entity(
        'tap',
        flow('pipe', SOURCE, SINK, unit='L/h', request=formula(ifelse(t <= q(2, 'h'), rate(4), rate(1)))),
        value('same', 'L/h', -1),
        value('next', 'L/h', -1),
        event(
            'look',
            after(q(at, 'h'), assign(this.same, this.pipe.actual_rate)),
            after(q(0, 'h'), assign(this.next, this.pipe.actual_rate)),
        ),
    )
    b.setup(start(named('tap').look))
    program = b.finish()
    record = run(program, Configuration(Request(3)))
    times = [float(at)]
    assert [
        reading.values
        for reading in read(record, program, ['tap.same', 'tap.next', 'tap.pipe.actual_rate'], times)
    ] == [(4,), (1,), (1,)]
    assert [mark.t for mark in record.entries('contact')] == times


@pytest.mark.parametrize('feedback', [False, True], ids=['quadratic', 'exponential'])
def test_a_curved_store_switches_an_outside_pipe_on_its_trajectory(feedback):
    """x(t) = t² reaches 1 L at 1 h. x(t) = exp(t) reaches 2 L at log(2) h."""
    import math

    b = Builder(UNITS)
    fill = this.water * q(1, '1/h') if feedback else t * q(2, 'L/h/h')
    b.entity(
        'tank',
        value('water', 'L', int(feedback), lower=0),
        flow('fill', SOURCE, this.water, request=formula(fill)),
    )
    before = named('tank').water <= q(2 if feedback else 1, 'L')
    b.entity('tap', flow('pipe', SOURCE, SINK, unit='L/h', request=formula(ifelse(before, rate(4), rate(1)))))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    target = key('tap.pipe.actual_rate')
    contact = math.log(2) if feedback else 1
    assert record.failure is None and not record.entries('contact')
    pieces = record.history(target).pieces
    assert [(piece.value, piece.rate) for piece in pieces] == [(4, 0), (1, 0)]
    assert pieces[1].t == pytest.approx(contact, abs=2e-7)
    assert read(record, program, [target], [contact - 1e-6, contact + 1e-6])[0].values == (4, 1)
    if not feedback:
        check(program, 2, [('tap.pipe.actual_rate', F(1, 2), 4), ('tap.pipe.actual_rate', F(3, 2), 1)])


@pytest.mark.parametrize('rising', [False, True])
def test_an_outside_table_reads_the_row_on_each_side_of_a_moving_store_key(rising):
    """Rising x(t)=t² and falling x(t)=2−t cross the 1 L key at 1 h."""
    b = Builder(UNITS)
    rows = b.template('Reading', input_('level', 'L', 0), input_('give', 'L/h', 0))
    b.table('readings', rows, ({'level': 0, 'give': 4}, {'level': 1, 'give': 1}))
    pipe = (
        flow('fill', SOURCE, this.water, request=formula(t * q(2, 'L/h/h')))
        if rising
        else flow('drain', this.water, SINK, request=rate(1))
    )
    b.entity('tank', value('water', 'L', 0 if rising else 2, lower=0), pipe)
    b.entity(
        'tap',
        flow(
            'pipe',
            SOURCE,
            SINK,
            unit='L/h',
            request=formula(rows.instances.by('level').at(named('tank').water).give),
        ),
        value('same', 'L/h', -1),
        value('next', 'L/h', -1),
        event(
            'copy',
            after(q(1, 'h'), assign(this.same, this.pipe.actual_rate)),
            after(q(0, 'h'), assign(this.next, this.pipe.actual_rate)),
        ),
    )
    b.setup(start(named('tap').copy))
    before, after_rate = (4, 1) if rising else (1, 4)
    check(
        b.finish(),
        F(3, 2),
        [('tap.same', 1, before), ('tap.next', 1, after_rate), ('tap.pipe.actual_rate', 1, after_rate)],
    )


def test_a_watched_condition_fires_when_an_outside_rate_changes_at_its_own_switch():
    b = Builder(UNITS)
    b.entity(
        'tap',
        flow('pipe', SOURCE, SINK, unit='L/h', request=formula(ifelse(t <= q(2, 'h'), rate(4), rate(1)))),
        value('seen', 'h', -1),
        event(
            'copy',
            when(this.pipe.actual_rate <= rate(2), start(this.copy), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.seen, t)),
        ),
    )
    check(b.finish(), 3, [('tap.seen', 1, -1), ('tap.seen', 2, 2), ('tap.seen', 3, 2)])


def test_a_watched_source_to_sink_rate_reaches_a_threshold_on_its_line():
    """The request rises by 1 L/h each hour and reaches 1 L/h after the first hour."""
    b = Builder(UNITS)
    b.entity(
        'tap',
        flow('pipe', SOURCE, SINK, unit='L/h', request=formula(t * q(1, 'L/h/h'))),
        value('seen', 'h', -1),
        event(
            'copy',
            when(this.pipe.actual_rate >= rate(1), start(this.copy), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.seen, t)),
        ),
    )
    check(b.finish(), 3, [('tap.seen', F(1, 2), -1), ('tap.seen', 1, 1), ('tap.seen', 3, 1)])


def test_a_deferred_delay_reads_the_outside_rate_just_shared_at_its_switch():
    b = Builder(UNITS)
    b.entity(
        'tap',
        flow('pipe', SOURCE, SINK, unit='L/h', request=formula(ifelse(t <= q(2, 'h'), rate(4), rate(1)))),
        value('seen', 'h', -1),
        event('copy', after(q(2, 'h')), after(this.pipe.actual_rate / q(1, 'L/h/h'), assign(this.seen, t))),
    )
    b.setup(start(named('tap').copy))
    check(b.finish(), 6, [('tap.seen', 2, -1), ('tap.seen', 3, 3), ('tap.seen', 6, 3)])


def test_an_outside_rate_at_a_nonlinear_clock_switch_is_the_new_branch():
    b = Builder(UNITS)
    before = t * t <= q(2, 'h') * q(2, 'h')
    b.entity('tap', flow('pipe', SOURCE, SINK, unit='L/h', request=formula(ifelse(before, rate(4), rate(1)))))
    program = b.finish()
    record = run(program, Configuration(Request(5)))
    assert not record.entries('contact')
    assert [record.value(key('tap.pipe.actual_rate'), at) for at in (1, 2, 4)] == [4, 1, 1]


def test_two_outside_switch_locations_on_one_pipe_are_reported_at_their_moment():
    b = Builder(UNITS)
    distance = F(1, 200000000)
    first, second = 2 - distance, 2 + distance
    ask = ifelse(t <= q(first, 'h'), rate(4), rate(1)) + ifelse(t <= q(second, 'h'), rate(6), rate(3))
    b.entity(
        'tap',
        flow('pipe', SOURCE, SINK, unit='L/h', request=formula(ask)),
        value('seen', 'L/h', -1),
        value('next', 'L/h', -1),
        event(
            'copy',
            after(q(2, 'h'), assign(this.seen, this.pipe.actual_rate)),
            after(q(0, 'h'), assign(this.next, this.pipe.actual_rate)),
        ),
    )
    b.setup(start(named('tap').copy))
    program = b.finish()
    record = run(program, Configuration(Request(3)))
    assert [record.value(key(path), 2) for path in ('tap.seen', 'tap.next', 'tap.pipe.actual_rate')] == [
        10,
        4,
        4,
    ]
    assert [(mark.t, mark.detail('located')) for mark in record.entries('contact')] == [
        (2, float(first)),
        (2, float(second)),
    ]


@pytest.mark.parametrize('kind', ['held', 'moving', 'key'])
def test_an_outside_pipe_keeps_the_shared_side_until_a_later_contact(kind):
    """The clock groups 2 h with the stage 5 billionths of an hour earlier. The next stage reads its side."""
    b = Builder(UNITS)
    at = F(2) - F(5, 10**9)
    delay = F(1, 10**9)
    if kind == 'key':
        b.entity('gauge', value('level', 'L', 0, lower=0), flow('fill', SOURCE, this.level, request=rate(1)))
        rows = b.template('Reading', input_('level', 'L', 0), input_('give', 'L/h', 0))
        b.table('readings', rows, ({'level': 0, 'give': 4}, {'level': 2, 'give': 1}))
        ask = rows.instances.by('level').at(named('gauge').level).give
    else:
        after_rate = rate(1) + (t - q(at, 'h')) * q(10**7, 'L/h/h') if kind == 'moving' else rate(1)
        ask = ifelse(t <= q(2, 'h'), rate(4), after_rate)
    b.entity(
        'tap',
        flow('pipe', SOURCE, SINK, unit='L/h', request=formula(ask)),
        value('first', 'L/h', -1),
        value('shared', 'L/h', -1),
        value('later', 'L/h', -1),
        event(
            'copy',
            after(q(at, 'h'), assign(this.first, this.pipe.actual_rate)),
            after(q(0, 'h'), assign(this.shared, this.pipe.actual_rate)),
            after(q(delay, 'h'), assign(this.later, this.pipe.actual_rate)),
        ),
    )
    b.setup(start(named('tap').copy))
    p = b.finish()
    config = Configuration(Request(2 + F(1, 10**6)))
    live = Run(Plan.of(p, config), (Breakpoint('tap.copy.step[1]'),))
    paused = live.run()
    assert isinstance(paused, Checkpoint)
    for result in (run(p, config), live.resume(), resume(p, loads(dumps(paused)))):
        assert result.failure is None
        assert result.value(key('tap.first'), float(at)) == 4
        assert result.value(key('tap.shared'), float(at)) == pytest.approx(1)
        expected = 1.01 if kind == 'moving' else 1
        for path in ('tap.later', 'tap.pipe.actual_rate'):
            assert result.value(key(path), float(at + delay)) == pytest.approx(expected, abs=1e-7), path


def test_a_new_switched_request_keeps_its_moving_arithmetic_in_the_record():
    b = Builder(UNITS)
    first = formula(rate(1) + t * q(1, 'L/h/h'))
    changed = formula(ifelse(t < q(2, 'h'), rate(5) + t * q(1, 'L/h/h'), rate(1) + t * q(2, 'L/h/h')))
    b.entity(
        'tap',
        flow('pipe', SOURCE, SINK, unit='L/h', request=first),
        event('change', after(q(1, 'h'), assign(this.pipe.request, changed))),
    )
    b.setup(start(named('tap').change))
    check(
        b.finish(),
        3,
        [
            ('tap.pipe.actual_rate', at, answer)
            for at, answer in ((F(1, 2), F(3, 2)), (1, 6), (F(3, 2), F(13, 2)), (2, 5), (F(5, 2), 6), (3, 7))
        ],
    )


@pytest.mark.parametrize(('asked', 'capacity', 'answer'), [(5, 3, 3), (-1, 3, -1), (5, -2, -2)])
def test_a_held_source_to_sink_pipe_has_its_own_set_on_lines(asked, capacity, answer):
    """With no endpoint claim the published rate is min(request, capacity)."""
    from napkin.engine.timeline.lines import Lines

    b = Builder(UNITS)
    b.entity('tap', flow('pipe', SOURCE, SINK, unit='L/h', request=rate(asked), capacity=rate(capacity)))
    p = b.finish()
    actual = key('tap.pipe.actual_rate')
    work = Run(Plan.of(p, Configuration(Request(2, keys=(actual,), everything=False))))
    result = work.run()
    assert result.failure is None
    way = work.ways.instance_of('tap.pipe')
    assert isinstance(way, Lines)
    assert [(part.stores, part.flows) for part in way.sets] == [((), ('tap.pipe',))]
    assert result.value(actual, 1) == answer
    assert result.history(key('tap.pipe.request')).at(1) == asked
    assert result.history(key('tap.pipe.capacity')).at(1) == capacity
