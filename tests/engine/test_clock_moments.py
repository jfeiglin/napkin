"""What a moment changes by itself, every reader of a rate, and a switch at the time of a moment
(PLAN, changes 25 and 26; spec, "Rounds" and "Reading a result").

In a moment the stages commit first and the flows are shared again after. A rate that the settling
decides (a flow's `actual_rate`, an endpoint's inflow or outflow) whose dependence changed by the clock
at the moment's time is stale until the settling, as one whose store met its bound there is: a keyed
read by the time at its key time, and a branch on the time or on a store whose condition changes at
that time. A read of it stops the run by name, whoever reads it: a stage, a firing's capture, the
argument of a start or a delay that a firing reaches after an earlier firing of the same conditions
started a flow that joins one of its stores. An assertion over state reads the settled state of a
round, before the firings start the consequences of the next one. And a run is the same whether a
crossing falls on a moment or not: a segment that starts a roundoff short of a switch that its state
crosses starts on the far side of it, and the rates that the settling gives at a moment are those that
hold from the moment on.

The rule test: small random networks of stores (empty, stocked, full), flows whose requests branch on
the time or on a store, or follow a keyed read by the time, with thresholds, rates and stage times
chosen so that crossings, key times and stages fall on one another as often as near one another;
stages that read a rate in the same round and in the next one; firings at the same time that start a
flow at a store and capture, pass or wait on a rate there; an assertion over an outflow. The oracle
(`tests/reference/`) runs the same program in exact fractions: both runs fail at the same time, a stale
read where the oracle's is one, or both pass with the same values. The same runs also stop before the
reading stage and edit a store there, resumed in place and from the saved state. The named cases
state the rule's words and its numbers, worked by hand.
"""

from __future__ import annotations

import random
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
from tests.engine.test_checkpoints import in_a_fresh_process
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of, value_at

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
STALE = 'is read before'  # the words of every stale read, of the engine and of the oracle
COMPARE = ('lt', 'le', 'gt', 'ge')
FACTORS = ({'hour': 0, 'factor': 1}, {'hour': 1, 'factor': 2}, {'hour': 2, 'factor': 1}, {'hour': 3, 'factor': 3})


def rate(number):
    return q(number, 'L/h')


def compared(op, left, right):
    return {'lt': left < right, 'le': left <= right, 'gt': left > right, 'ge': left >= right}[op]


def network(seed):
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
    reads += [getattr(level(s), side).actual_rate for s in ends for side in ('outflow', 'inflow') if (s, side) in met]
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
            event('deliver', pipe, after(q(1, 'h')), when(t >= at, start(this.deliver), reset=reset_when(False)))
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
            note = when(t >= at, start(this.note, watched if how == 'argument' else rate(1)), reset=reset_when(False))
        delay = watched * q(1, 'h*h/L') if how == 'delay' else q(0, 'h')
        if how != 'none':
            parts.append(
                event('note', param('copy', 'L/h'), after(delay, assign(named('ops').noted, local.copy)), note)
            )
    if rng.random() < 0.3:
        parts.append(assertion(level(delivered).outflow.actual_rate <= rate(rng.choice([2, 6]))))
    b.entity('ops', *parts)
    b.setup(start(named('ops').look))
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
    for record in engine_records(program, configuration, change if edit else None):
        message = None if record.failure is None else record.failure.detail('message')
        if oracle is None:  # the setup fails
            assert message is not None and record.failure.t == 0, (seed, str(failed))
            continue
        if failed is not None:
            assert message is not None, (seed, str(failed))
            assert record.failure.t == pytest.approx(float(oracle.view.t)), (seed, str(failed), message)
            assert (STALE in message) == (STALE in str(failed)), (seed, str(failed), message)
            horizon = oracle.view.t - Fraction(1, 10**9)  # what happens at the failure is not compared
        else:
            assert message is None, (seed, message)
            horizon = Fraction(HORIZON)
        times = [time for time in TIMES if time < horizon]
        for key in keys:
            found = read(record, program, [key], [float(time) for time in times])[0].values
            for time, number in zip(times, found):
                expected = float(value_at(oracle, program, key, time))
                assert number == pytest.approx(expected, rel=1e-9, abs=1e-9), (seed, str(key), float(time))


@pytest.mark.parametrize('seed', range(200))
def test_a_moment_s_own_changes_and_every_reader_agree_with_the_oracle(seed):
    compare(seed)


@pytest.mark.parametrize('seed', range(200))
def test_an_edit_at_a_stop_before_the_read_agrees_in_place_and_resumed(seed):
    compare(seed, edit=True)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(200, 2200))
def test_more_moments_and_readers_agree_with_the_oracle(seed):
    compare(seed)
    compare(seed, edit=True)
