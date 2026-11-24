"""The first round at a new time reads the incoming rates at key times, switches and bounds.

The flows share again after the stages. Later rounds at that time read the preceding round's share.
Firings and assertions read that sharing. Occurrences a firing starts join the next sharing, and a
delay that depends on them waits for it (docs/design/decisions.md, change 27). On leaving a switch, integration follows
the far side from the start of its segment.

Small random networks put stages, changes of branch, key times and firings at the same times. The
engine and interpreter compare their readings and the water in their stores, straight through
and after an edit and a resume. The named cases give the rates and levels worked by hand.
"""

from __future__ import annotations

import random
from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run, resume
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    after,
    assertion,
    assign,
    endpoint,
    event,
    flow,
    fmin,
    formula,
    ifelse,
    input_,
    local,
    named,
    param,
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
from tests.engine.resume_parity import assert_resume_parity
from tests.engine.test_checkpoints import in_a_fresh_process
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of, value_at, values_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
HORIZON = 4
TIMES = [Fraction(k, 4) for k in range(4 * HORIZON + 1)]
STORES = {  # start, lower, upper
    'empty': (0, 0, None),
    'stocked': (6, 0, None),
    'full': (8, 0, 8),
    'small': (2, 0, 10),
}
LOOK = 'ops.look.step[0]'  # the reading stage, where the runs with an edit stop
# A component refuses a store that rests on a bound between flows whose rates move where local
# sharing could raise a flow above its request (`component.Held`): the engine has no answer there.
NO_ANSWER = ('rests on a bound between a flow in and a flow out',)
COMPARE = ('lt', 'le', 'gt', 'ge')
FACTORS = (
    {'hour': 0, 'factor': 1},
    {'hour': 1, 'factor': 2},
    {'hour': 2, 'factor': 1},
    {'hour': 3, 'factor': 3},
)


def rate(number):
    return q(number, 'L/h')


def compared(op, left, right):
    return {'lt': left < right, 'le': left <= right, 'gt': left > right, 'ge': left >= right}[op]


def network(seed, *, empty_time=None):
    """A random program (see the module): stores `s<k>.water`, flows `f<k>.pipe`, the table
    `readings`, and the operator `ops`, whose events read the rates. Gives the program, the keys to
    compare, and an edit of a store (its key and a level within its bounds)."""
    rng = random.Random(seed)
    b = Builder(UNITS)
    readings = b.template('Reading', input_('hour', 'h', 0), input_('factor', '', 1))
    b.table('readings', readings, FACTORS)
    factor = readings.instances.by('hour').at(t).factor
    count = rng.randint(1, 2)
    kinds = [rng.choice(list(STORES)) for _ in range(count)]
    ends = list(range(count))

    def level(s):
        return named(f's{s}').water

    def request():
        """A request whose condition changes at a time that a stage or a key time meets often."""
        r1, r2 = rng.choice([0, Fraction(1, 2), 1, 2]), rng.choice([Fraction(1, 2), 1, 2, 3])
        kind = rng.choice(['constant', 'time', 'time', 'store', 'store', 'keyed', 'least'])
        if kind == 'constant':
            return rate(r2)
        if kind == 'time':
            test = compared(rng.choice(COMPARE), t, q(rng.choice([1, 2, 3]), 'h'))
            return formula(ifelse(test, rate(r1), rate(r2)))
        if kind == 'store':
            test = compared(rng.choice(COMPARE), level(rng.choice(ends)), q(rng.choice([1, 2, 4, 6, 8]), 'L'))
            return formula(ifelse(test, rate(r1), rate(r2)))
        if kind == 'keyed':
            return formula(factor * rate(r2))
        return formula(fmin(rate(r2), ifelse(t >= q(rng.choice([1, 2, 3]), 'h'), rate(r1), rate(3))))

    flows = []
    for _ in range(rng.randint(1, 3)):
        source = rng.choice([None, None, *ends])
        sink = rng.choice([s for s in [None, *ends] if s != source or s is None])
        if source is None and sink is None:
            sink = rng.choice(ends)
        flows.append((source, sink, request()))
    for s, kind in enumerate(kinds):
        start_level, lower, upper = STORES[kind]
        capacity = rng.choice([None, None, None, rate(3)])
        b.entity(
            f's{s}',
            value('water', 'L', start_level, lower=lower, upper=upper, outflow=endpoint(capacity=capacity)),
        )

    def end(s, outside):
        return outside if s is None else level(s)

    for k, (source, sink, asked) in enumerate(flows):
        b.entity(f'f{k}', flow('pipe', end(source, SOURCE), end(sink, SINK), request=asked))

    # The pipe of an occurrence of `deliver` drains `delivered`: its outflow has a flow to read.
    delivered = rng.choice(ends)
    met = {(delivered, 'outflow')}
    for source, sink, _ in flows:
        met |= {(source, 'outflow'), (sink, 'inflow')}
    reads = [named(f'f{k}').pipe.actual_rate for k in range(len(flows))]
    reads += [
        getattr(level(s), side).actual_rate
        for s in ends
        for side in ('outflow', 'inflow')
        if (s, side) in met
    ]
    picked = rng.choice(reads)
    # The reading stage, at a time that crossings and key times meet often, and the next round's.
    looking = [after(q(rng.choice([1, 2, 2, 3]), 'h'), assign(this.seen, rng.choice([picked, this.twice])))]
    if rng.random() < 0.5:
        looking.append(after(q(0, 'h'), assign(this.again, picked)))
    parts = [
        value('seen', 'L/h', -1),
        value('again', 'L/h', -1),
        value('noted', 'L/h', -1),
        value('twice', 'L/h', formula(picked * 2)),
        event('look', *looking),
    ]
    # Two firings at one time: the first starts `deliver`, whose pipe joins a store; the second
    # captures, passes or waits on a rate (read after the first, before the flows settle again).
    if rng.random() < 0.6:
        at = q(rng.choice([1, 2, 3]), 'h')
        pipe = flow('pipe', level(delivered), SINK, request=rate(rng.choice([1, 2])))
        parts.append(
            event(
                'deliver', pipe, after(q(1, 'h')), when(t >= at, start(this.deliver), reset=reset_when(False))
            )
        )
        watched = rng.choice([picked, level(delivered).outflow.actual_rate])
        how = rng.choice(['capture', 'argument', 'delay', 'none'])
        if how == 'capture':
            note = when(
                t >= at,
                start(this.note, local.got),
                reset=reset_when(False),
                captures=(value('got', 'L/h', watched),),
            )
        else:
            note = when(
                t >= at, start(this.note, watched if how == 'argument' else rate(1)), reset=reset_when(False)
            )
        delay = watched * q(1, 'h*h/L') if how == 'delay' else q(0, 'h')
        if how != 'none':
            parts.append(
                event(
                    'note', param('copy', 'L/h'), after(delay, assign(named('ops').noted, local.copy)), note
                )
            )
    b.entity('ops', *parts)
    b.setup(start(named('ops').look))
    if empty_time is not None:
        idle = b.entity('unrelated', event('wait', after(q(empty_time, 'h'))))
        b.setup(start(idle.wait))
    keys = [Key(f's{s}', ('water',)) for s in ends] + [
        Key('ops', (name,)) for name in ('seen', 'again', 'noted')
    ]
    edited = rng.choice(ends)
    _, lower, upper = STORES[kinds[edited]]
    return b.finish(), keys, (Key(f's{edited}', ('water',)), rng.choice([lower, upper or 5]))


def engine_records(program, configuration, edit):
    """The engine's records of a program: straight through, or with `edit` made at a stop before the
    reading stage, resumed in place and from the checkpoint's saved state (what a fresh process
    loads)."""
    if edit is None:
        return [run(program, configuration)]
    made = Run(Plan.of(program, configuration), (Breakpoint(LOOK),))
    found = made.run()
    if not isinstance(found, Checkpoint):
        return [found]
    edited = made.edit(*edit)
    return [made.resume(), resume(program, loads(dumps(edited)))]


def compare(seed, edit=False):
    program, keys, change = network(seed)
    configuration = Configuration(Request(HORIZON))
    try:
        oracle, failed = run_of(program, configuration, [(LOOK, None, [change])] if edit else [])
    except NotCovered:
        return
    expected = None
    paths = ('edited in place', 'edited from a checkpoint') if edit else ('straight through',)
    for path, record in zip(paths, engine_records(program, configuration, change if edit else None)):
        message = None if record.failure is None else record.failure.detail('message')
        if message is not None and any(reason in message for reason in NO_ANSWER):
            continue
        if oracle is None:  # the setup fails
            assert message is not None and record.failure.t == 0, (seed, str(failed))
            continue
        if failed is not None:
            assert message is not None, (seed, str(failed))
            assert record.failure.t == pytest.approx(float(oracle.view.t)), (seed, str(failed), message)
            horizon = oracle.view.t - Fraction(1, 10**9)  # what happens at the failure is not compared
        else:
            assert message is None, (seed, message)
            horizon = Fraction(HORIZON)
        times = [time for time in TIMES if time < horizon]
        if expected is None:
            expected = values_at(oracle, program, keys, times)
        readings = read(record, program, keys, list(map(float, times)))
        for key, row in zip(keys, readings, strict=True):
            for time, number, target in zip(times, row.values, expected[key], strict=True):
                # The sets whose rates move run on Radau: the values agree to its accuracy.
                assert number == pytest.approx(float(target), rel=1e-7, abs=1e-7), (
                    seed,
                    path,
                    str(key),
                    float(time),
                )


@pytest.mark.parametrize('seed', range(200))
def test_a_moment_s_own_changes_and_every_reader_agree_with_the_oracle(seed):
    compare(seed)


@pytest.mark.parametrize('seed', range(200))
def test_an_edit_at_a_stop_before_the_read_agrees_in_place_and_resumed(seed):
    compare(seed, edit=True)


@pytest.mark.parametrize(('method', 'seed'), [('component', 1218), ('sparse', 1218), ('sparse', 424)])
def test_a_retiring_group_closes_its_own_legs_before_an_occurrence_joins(method, seed, monkeypatch):
    # These stops add ops.deliver#0.pipe at a capped endpoint. A correction on the
    # incoming group can use only the legs it carried before the join.
    connect = Plan.connect

    def force(plan, *args, **kwargs):
        return [
            replace(group, way=method) if group.way == 'sparse' else group
            for group in connect(plan, *args, **kwargs)
        ]

    monkeypatch.setattr(Plan, 'connect', force)
    compare(seed)
    compare(seed, edit=True)


def test_an_opening_checkpoint_keeps_the_incoming_rates_that_justify_its_balance():
    # The accepted left rates are all zero when ops.look stops at 2 h. Re-evaluating
    # the field at its old step start would invent a proportional outgoing correction.
    program, _, edit = network(2120)
    config = Configuration(Request(HORIZON))
    machine = Run(Plan.of(program, config), [Breakpoint(LOOK)])
    stopped = machine.run()
    assert isinstance(stopped, Checkpoint) and stopped.stop.t == 2
    crumb = machine.stock_balance('s1.water', 2)
    # The crumb is roundoff: positive, zero or negative in its last places by platform and
    # kernel, and a level within its comparison band of zero is at zero.
    assert abs(crumb) <= machine.comparison_band('s1.water', float(crumb), 0)
    edited = machine.edit(*edit)
    restored = Run.restored(Plan.of(program, config), loads(dumps(edited)))
    assert restored.stock_balance('s1.water', 2) == crumb
    assert_resume_parity(program, config, machine.resume(), restored.resume())


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(200, 2200))
def test_more_moments_and_readers_agree_with_the_oracle(seed):
    compare(seed)
    compare(seed, edit=True)


# ---- the named cases, worked by hand -----------------------------------------------------------------


def plant(request, *stages, horizon=4):
    """An empty plant `water` in [0, inf) filled from outside at `request`, and an operator whose event
    `look` runs `stages`: the program and its record."""
    b = Builder(UNITS)
    b.entity('plant', value('water', 'L', 0, lower=0), flow('fill', SOURCE, this.water, request=request))
    b.entity(
        'ops',
        value('seen', 'L/h', -1),
        value('again', 'L/h', -1),
        event('look', *stages),
    )
    b.setup(start(named('ops').look))
    program = b.finish()
    return program, run(program, Configuration(Request(horizon)))


FILL = named('plant').fill.actual_rate
plant_water = named('plant').water


def failure(record):
    """(the time of the failure of a run, its message), or (None, '') for a run that finished."""
    return (None, '') if record.failure is None else (record.failure.t, record.failure.detail('message'))


def values(program, record, path, times):
    return list(read(record, program, [path], times)[0].values)


@pytest.mark.parametrize('op', ['lt', 'le'])
def test_a_branch_on_the_time_at_a_stage_s_time_changes_the_next_rounds_rate(op):
    """Both comparisons read 1 L/h in the stage at the switch and 3 L/h after the sharing."""
    request = formula(ifelse(compared(op, t, q(2, 'h')), rate(1), rate(3)))
    program, record = plant(request, after(q(2, 'h'), assign(named('ops').seen, FILL)))
    assert failure(record)[0] is None and values(program, record, 'ops.seen', [2]) == [pytest.approx(1)]
    program, record = plant(request, after(q(2, 'h')), after(q(0, 'h'), assign(named('ops').seen, FILL)))
    assert failure(record)[0] is None
    assert values(program, record, 'ops.seen', [2]) == [pytest.approx(3)]
    assert values(program, record, 'plant.water', [2, 3]) == [pytest.approx(2), pytest.approx(5)]
    program, record = plant(request, after(q(1, 'h'), assign(named('ops').seen, FILL)))
    assert failure(record)[0] is None and values(program, record, 'ops.seen', [1]) == [pytest.approx(1)]


def test_a_keyed_read_at_its_key_time_changes_the_next_rounds_rate():
    """At 3 h the factor steps from 1 to 3. The stage reads 1 L/h and the next round reads 3."""
    for delay, then, expected in ((q(3, 'h'), None, 1), (q(3, 'h'), q(0, 'h'), 3), (q(2.5, 'h'), None, 1)):
        b = Builder(UNITS)
        readings = b.template('Reading', input_('hour', 'h', 0), input_('factor', '', 1))
        b.table('readings', readings, FACTORS)
        request = formula(readings.instances.by('hour').at(t).factor * rate(1))
        b.entity('plant', value('water', 'L', 0, lower=0), flow('fill', SOURCE, this.water, request=request))
        stages = (
            [after(delay, assign(this.seen, FILL))]
            if then is None
            else [after(delay), after(then, assign(this.seen, FILL))]
        )
        b.entity('ops', value('seen', 'L/h', -1), event('look', *stages))
        b.setup(start(named('ops').look))
        program = b.finish()
        record = run(program, Configuration(Request(4)))
        assert failure(record)[0] is None
        assert values(program, record, 'ops.seen', [3.5]) == [pytest.approx(expected)]


@pytest.mark.parametrize('test', ['lt', 'le'])
def test_a_branch_on_a_store_whose_crossing_falls_on_a_stage_s_time(test):
    """Below 2 L the rate is 1 L/h. The stage at that level reads 1, the next round reads 3."""
    request = formula(ifelse(compared(test, plant_water, q(2, 'L')), rate(1), rate(3)))
    program, record = plant(request, after(q(2, 'h'), assign(named('ops').seen, FILL)))
    assert failure(record)[0] is None and values(program, record, 'ops.seen', [2]) == [pytest.approx(1)]
    for stages in ([after(q(2, 'h'), assign(named('ops').again, rate(7)))], [after(q(0.5, 'h'))], []):
        program, record = plant(request, *stages)
        assert failure(record)[0] is None, failure(record)
        found = values(program, record, 'plant.water', [1, 2, 3, 4])
        assert found == [pytest.approx(x, abs=1e-8) for x in (1, 2, 5, 8)]
    program, record = plant(request, after(q(2, 'h')), after(q(0, 'h'), assign(named('ops').seen, FILL)))
    assert failure(record)[0] is None and values(program, record, 'ops.seen', [2]) == [pytest.approx(3)]


def test_a_switch_that_holds_its_store_changes_its_rate_after_the_stages():
    """The plant fills at 1 L/h to 2 L. The stage there reads 1 L/h, then the plant stops filling."""
    request = formula(ifelse(plant_water >= q(2, 'L'), rate(0), rate(1)))
    program, record = plant(request, after(q(2, 'h'), assign(named('ops').seen, FILL)))
    assert failure(record)[0] is None and values(program, record, 'ops.seen', [2]) == [pytest.approx(1)]
    for stages, at in (
        ([after(q(3, 'h'), assign(named('ops').seen, FILL))], 3),
        ([after(q(2, 'h')), after(q(0, 'h'), assign(named('ops').seen, FILL))], 2),
    ):
        program, record = plant(request, *stages)
        assert failure(record)[0] is None, failure(record)
        assert values(program, record, 'ops.seen', [at]) == [pytest.approx(0, abs=1e-9)]
        assert values(program, record, 'plant.water', [2, 4]) == [pytest.approx(2), pytest.approx(2)]


def test_a_switch_whose_far_side_carries_the_store_back_still_stops_with_chattering():
    """3 L/h in below 2 L, nothing above, and 1 L/h out: the plant reaches 2 L at 1 h, where each
    side takes it back across the switch; the run stops there, naming the switch."""
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('water', 'L', 0, lower=0),
        flow('fill', SOURCE, this.water, request=formula(ifelse(this.water < q(2, 'L'), rate(3), rate(0)))),
        flow('use', this.water, SINK, request=rate(1)),
    )
    record = run(b.finish(), Configuration(Request(4)))
    at, message = failure(record)
    assert (
        at == pytest.approx(1, abs=1e-6) and 'switch back and forth' in message and 'plant.water' in message
    )


def deliveries(*parts, capacity=2):
    """A tank of 8 L whose outflow carries at most `capacity` L/h, drained by `main` (2 L/h), and an
    operator whose `deliver` starts at 1 h from a trigger: its pipe (2 L/h) joins the tank's outflow.
    `parts` are the operator's other parts."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 8, lower=0, upper=20, outflow=endpoint(capacity=rate(capacity))),
        flow('main', this.water, SINK, request=rate(2)),
    )
    deliver = event(
        'deliver',
        flow('pipe', named('tank').water, SINK, request=rate(2)),
        after(q(1, 'h')),
        when(t >= q(1, 'h'), start(this.deliver), reset=reset_when(False)),
    )
    b.entity('ops', value('noted', 'L/h', -1), value('at', 'h', -1), deliver, *parts)
    return b


MAIN = named('tank').main.actual_rate


def note(trigger, *steps):
    return event('note', param('copy', 'L/h'), *steps, trigger)


@pytest.mark.parametrize('how', ['capture', 'argument'])
def test_a_firing_reads_the_shared_rate_after_an_earlier_firing_started_a_flow(how):
    """Main gets 2 L/h before the fired occurrence joins. Both captures and start arguments read 2."""
    if how == 'capture':
        trigger = when(
            t >= q(1, 'h'),
            start(this.note, local.got),
            reset=reset_when(False),
            captures=(value('got', 'L/h', MAIN),),
        )
    else:
        trigger = when(t >= q(1, 'h'), start(this.note, MAIN), reset=reset_when(False))
    b = deliveries(note(trigger, after(q(0, 'h'), assign(named('ops').noted, local.copy))))
    program = b.finish()
    record = run(program, Configuration(Request(3)))
    assert failure(record)[0] is None
    assert values(program, record, 'ops.noted', [1]) == [pytest.approx(2)]
    oracle, failed = run_of(program, Configuration(Request(3)))
    assert failed is None and value_at(oracle, program, Key('ops', ('noted',)), Fraction(1)) == 2


def test_a_delay_that_a_firing_reaches_waits_for_the_settling():
    """`note`, started at 1 h after `deliver`, waits main's rate times 1 h²/L: main gets 1 L/h of the
    outflow's 2 L/h once the pipe joins, so its stage is due at 2 h (on HEAD the engine read the 2 L/h
    of before and the stage came at 3 h, the oracle at 2 h)."""
    trigger = when(t >= q(1, 'h'), start(this.note, rate(1)), reset=reset_when(False))
    stage = after(MAIN * q(1, 'h*h/L'), assign(named('ops').at, t))
    program = deliveries(note(trigger, stage)).finish()
    record = run(program, Configuration(Request(3)))
    assert failure(record)[0] is None
    assert values(program, record, 'ops.at', [2.5]) == [pytest.approx(2)]
    oracle, failed = run_of(program, Configuration(Request(3)))
    assert failed is None and value_at(oracle, program, Key('ops', ('at',)), Fraction(5, 2)) == 2


@pytest.mark.parametrize(('limit', 'fails'), [(2, False), (3, True)])
def test_an_assertion_reads_the_settled_state_of_its_round(limit, fails):
    """The outflow carries at most `limit` L/h, and an assertion holds it to 2 L/h. At 1 h `deliver`'s
    pipe joins: the assertion reads the state that the round settled before the firing acts, and the
    next round's: with a limit of 2 L/h main and the pipe share 2 L/h and it holds; with 3 L/h they
    take 3 L/h and it fails at 1 h, as an assertion on the re-shared outflow."""
    b = deliveries(capacity=limit)
    b.entity('watch', assertion(named('tank').water.outflow.actual_rate <= rate(2)))
    program = b.finish()
    record = run(program, Configuration(Request(3)))
    oracle, failed = run_of(program, Configuration(Request(3)))
    at, message = failure(record)
    if not fails:
        assert at is None and failed is None
        return
    assert at == 1 and 'the assertion does not hold' in message
    assert failed is not None and 'assert' in str(failed) and oracle.view.t == 1


def test_a_stop_at_a_switch_keeps_the_incoming_rate_in_place_and_in_a_fresh_process(tmp_path):
    """On either resume, the stage at the plant's 2 L switch reads the incoming 1 L/h."""
    request = formula(ifelse(plant_water < q(2, 'L'), rate(1), rate(3)))
    program, _ = plant(request, after(q(2, 'h'), assign(named('ops').seen, FILL)))
    configuration = Configuration(Request(4))
    made = Run(Plan.of(program, configuration), (Breakpoint(LOOK),))
    stopped = made.run()
    assert isinstance(stopped, Checkpoint) and stopped.stop.t == 2
    for record in (made.resume(), *in_a_fresh_process(program, [stopped], tmp_path)):
        assert failure(record)[0] is None
        assert values(program, record, 'ops.seen', [2]) == [pytest.approx(1)]
