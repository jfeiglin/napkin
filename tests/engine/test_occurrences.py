"""Small random programs with events, against the oracle (`tests/reference/`).

Each case has a few tanks: stores with bounds, entity flows that fill, drain or pass water between
them at constant requests, sometimes an outflow capacity, and a counter. Their events start from the
setup and from triggers: a clock (`when t >= T`, with `reset after P` or once), a level on a tank
(`when water <= L` or `>= H`, with a reset or none). An event's occurrence may own a pipe from its
tank (to the outside or to another tank), whose flow joins the network at its start and leaves at
its finish; own a batch that a move fills and a flow empties; wait a delay or at a gate on a level;
and run stages that add to its tank, take from it, move water between tanks and count; a stage may
be guarded, and a trigger may watch, the time since a start of another tank's work, behind a count of
its occurrences that is false before the first (the guard short-circuits). Requests and levels are
whole numbers and halves, and rates are
powers of two, so every time at which something happens is a sum of powers of two: the engine's
times are exact, and the order of what happens at one time is the oracle's.

The oracle runs the same program in exact fractions. The values of the stores and the counters at
each half hour, the times of the starts, finishes and firings, and a failure (a bound that a write or
a move breaks, a store that is not empty when its occurrence finishes) with its time must agree.
"""

from __future__ import annotations

import random
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.program.artifact import Artifact, loads
from napkin.program.build import (
    BOOL,
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    count,
    endpoint,
    event,
    flow,
    formula,
    local,
    move,
    named,
    priority,
    proportional,
    q,
    reset_after,
    reset_when,
    since,
    start,
    subtract,
    t,
    this,
    until,
    value,
    when,
)
from napkin.program.checkpoint import decode, encode
from napkin.program.config import Configuration, Limits, Request
from napkin.program.record import Key
from tests.program.examples import EXAMPLES, At
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of, traced, value_at, values_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
HORIZON = 8
TIMES = [Fraction(k, 2) for k in range(2 * HORIZON + 1)]
RATES = (Fraction(1, 2), 1, 2, 4)


def _level(rng, low=0, high=12):
    return Fraction(rng.randint(2 * low, 2 * high), 2)


def program(seed):
    """A random program with events (see the module), and the keys of the values to compare."""
    rng = random.Random(seed)
    b = Builder(UNITS)
    number = rng.randint(1, 3)
    tanks = [f't{k}' for k in range(number)]
    caps = {name: (_level(rng, 8, 16) if rng.random() < 0.5 else None) for name in tanks}
    events = {name: [] for name in tanks}
    flows = {name: [] for name in tanks}
    for name in tanks:
        kind = rng.choice(('fill', 'drain', 'pass', 'none', 'none'))
        rate = q(rng.choice(RATES), 'L/h')
        if kind == 'fill':
            flows[name].append(flow('fill', SOURCE, this.water, request=rate))
        elif kind == 'drain':
            flows[name].append(flow('drain', this.water, SINK, request=rate))
        elif kind == 'pass' and number > 1:
            other = rng.choice([each for each in tanks if each != name])
            flows[name].append(flow('pass', this.water, named(other).water, request=rate))
    for name in tanks:
        other = named(rng.choice(tanks))
        parts = []
        if rng.random() < 0.5:
            sink = rng.choice((SINK, other.water))
            parts.append(flow('pipe', this.water, sink, request=q(rng.choice(RATES), 'L/h')))
        delay = q(rng.choice((Fraction(1, 2), 1, Fraction(3, 2), 2)), 'h')
        body = []
        if rng.random() < 0.25:
            # A batch of the occurrence's own, which a move fills and a flow empties: it must be
            # empty when the occurrence finishes.
            parts.append(value('batch', 'L', 0, lower=0))
            out = rng.choice((SINK, other.water))
            parts.append(flow('out', local.batch, out, request=q(rng.choice(RATES), 'L/h')))
            body.append(move(q(_level(rng, 0, 3), 'L'), this.water, local.batch))
        for _ in range(rng.randint(0, 2)):
            what = rng.random()
            if what < 0.3:
                body.append(add(this.water, q(_level(rng, 0, 4), 'L')))
            elif what < 0.5:
                body.append(subtract(this.water, q(_level(rng, 0, 3), 'L')))
            elif what < 0.7:
                body.append(move(q(_level(rng, 0, 3), 'L'), this.water, other.water))
            else:
                body.append(add(this.served, 1))
        # A guard that short-circuits: `since` of another tank's work has no value before its start.
        started = (count(other.work.occurrences) > 0) & (since(other.work) >= q(rng.choice((1, 2)), 'h'))
        steps = [after(delay, *body, when=started if rng.random() < 0.2 else None)]
        if rng.random() < 0.3:
            steps.append(until(this.water >= q(_level(rng, 0, 10), 'L')))
        if rng.random() < 0.3:
            steps.append(after(q(rng.choice((Fraction(1, 2), 1)), 'h'), add(this.served, 1)))
        triggers = []
        trigger = rng.random()
        if trigger < 0.35:
            reset = reset_after(q(rng.choice((1, 2, 3)), 'h')) if rng.random() < 0.6 else reset_when(False)
            clock = t >= q(rng.choice((1, 2, 3, Fraction(5, 2))), 'h')
            triggers.append(when(clock, start(this.work), reset=reset))
        elif trigger < 0.7:
            mark = q(_level(rng, 0, 12), 'L')
            test = this.water <= mark if rng.random() < 0.5 else this.water >= mark
            choice = rng.random()
            if choice < 0.3:
                reset = None
            elif choice < 0.6:
                reset = reset_when(this.water >= q(_level(rng, 0, 12), 'L'))
            else:
                reset = reset_after(q(rng.choice((1, 2)), 'h'))
            triggers.append(when(test, start(this.work), reset=reset))
        elif trigger < 0.85:
            # A condition on the time since a start of another tank's work, false before its first.
            mark = q(rng.choice((Fraction(1, 2), 1, 2)), 'h')
            test = (count(other.work.occurrences) > 0) & (since(other.work) >= mark)
            triggers.append(when(test, start(this.work), reset=reset_after(q(rng.choice((1, 2)), 'h'))))
        events[name].append(event('work', *parts, *steps, *triggers))
    for name in tanks:
        outflow = endpoint(capacity=q(rng.choice((1, 2, 3)), 'L/h')) if rng.random() < 0.25 else None
        b.entity(
            name,
            value(
                'water',
                'L',
                min(_level(rng, 0, 10), caps[name] or 10),
                lower=0,
                upper=caps[name],
                outflow=outflow,
            ),
            value('served', '', 0),
            *flows[name],
            *events[name],
        )
    b.setup(*[start(named(name).work) for name in tanks if rng.random() < 0.6])
    keys = [Key(name, ('water',)) for name in tanks] + [Key(name, ('served',)) for name in tanks]
    return b.finish(), keys, [f'{name}.work' for name in tanks]


def compare(seed):
    source, keys, events = program(seed)
    # A trigger whose reset holds while its condition does fires again in each round: the limits of
    # rounds at one time and of active occurrences (D6) stop it, in both runs, after a few.
    configuration = Configuration(Request(HORIZON), limits=Limits(max_active=8, max_rounds=12))
    try:
        oracle, failed = run_of(source, configuration)
    except NotCovered:
        return
    record = run(source, configuration)
    if oracle is None:  # the setup fails
        assert record.failure is not None and record.failure.t == 0, (seed, str(failed))
        return
    if failed is not None:
        assert record.failure is not None, (seed, str(failed))
        assert record.failure.t == pytest.approx(float(oracle.view.t)), (seed, str(failed), record.failure)
        # What happens at the time of the failure is not compared: its float time can be a hair
        # below the oracle's exact one.
        horizon = oracle.view.t - Fraction(1, 10**9)
    else:
        assert record.failure is None, (seed, record.failure.detail('message'))
        horizon = Fraction(HORIZON)
    for kind in ('start', 'finish'):
        for name in events:
            found = [entry.t for entry in record.entries(kind, name) if entry.t < horizon]
            expected = [float(t) for t, _ in traced(oracle, kind, name) if t < horizon]
            assert found == pytest.approx(expected), (seed, kind, name)
    for name in events:
        part = f'{name}.when[0]'
        found = [entry.t for entry in record.entries('fire', part) if entry.t < horizon]
        expected = [float(t) for t, _ in traced(oracle, 'fire', part) if t < horizon]
        assert found == pytest.approx(expected), (seed, 'fire', part)
    times = [time for time in TIMES if time < horizon]
    exact = values_at(oracle, source, keys, times)
    rows = read(record, source, keys, list(map(float, times)))
    for key, row in zip(keys, rows, strict=True):
        for time, number, expected in zip(times, row.values, exact[key], strict=True):
            assert number == pytest.approx(float(expected), rel=1e-9, abs=1e-9), (seed, str(key), float(time))


@pytest.mark.parametrize('seed', range(300))
def test_a_small_random_program_with_events_runs_as_the_oracle_does(seed):
    compare(seed)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(300, 2300))
def test_more_random_programs_with_events_run_as_the_oracle_does(seed):
    compare(seed)


@pytest.mark.parametrize(
    'name', ['deliveries_current_flows', 'grinder_trigger_and_manual', 'frozen_formula', 'rising_ramp']
)
def test_a_record_read_without_its_run_makes_its_occurrences_again_from_its_trace(name):
    """A reader that has not the plan of the run that made a record (a stored record, or another run
    of the program since) makes the record's occurrences again from the starts of its trace, and
    reads the same values."""
    example = EXAMPLES[name]()
    record = run(example.program, example.configuration)
    keys = [item.key for item in example.expected if isinstance(item, At)]
    times = sorted({float(item.t) for item in example.expected if isinstance(item, At)})
    first = [reading.values for reading in read(record, example.program, keys, times)]
    saved = decode(encode(record))
    program = loads(Artifact(example.program).data()).program
    again = [reading.values for reading in read(saved, program, keys, times)]
    assert again == first


def limited(limits, *steps):
    """A plant whose clock starts `inspect` every hour from 1 h; each occurrence runs `steps`."""
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('cleared', BOOL, False),
        event('inspect', *steps, when(t >= q(1, 'h'), start(this.inspect), reset=reset_after(q(1, 'h')))),
    )
    return run(b.finish(), Configuration(Request(HORIZON), limits=limits))


def test_the_limit_of_active_occurrences_names_the_oldest_and_where_it_waits():
    # A gate that never opens keeps every inspection active: the sixth start, at 6 h, is one too many.
    record = limited(Limits(max_active=5), until(this.cleared))
    message = record.failure.detail('message')
    assert record.failure.t == 6
    assert '5 occurrences of plant.inspect are active at once (max_active = 5)' in message
    assert 'The oldest, plant.inspect#0, started at 1 h and waits at `until this.cleared`' in message


def test_the_limit_of_starts_of_one_event_counts_finished_occurrences_too():
    record = limited(Limits(max_occurrences=3), after(q(0, 'h')))
    assert record.failure.t == 4 and 'max_occurrences is 3' in record.failure.detail('message')


def test_the_limit_of_rounds_at_one_time_names_the_events_that_started_then():
    # A trigger whose reset holds while its condition does fires again in each round at 1 h.
    b = Builder(UNITS)
    b.entity(
        'plant', event('inspect', when(t >= q(1, 'h'), start(this.inspect), reset=reset_when(t >= q(0, 'h'))))
    )
    record = run(b.finish(), Configuration(Request(HORIZON), limits=Limits(max_rounds=5)))
    message = record.failure.detail('message')
    assert record.failure.t == 1 and 'max_rounds is 5' in message and 'plant.inspect (5 starts)' in message


@pytest.mark.parametrize('name', ['deliveries_current_flows', 'frozen_formula', 'rising_ramp'])
def test_a_record_of_some_keys_keeps_what_their_occurrences_and_collections_need(name):
    """A record that keeps only the keys that an example states reads them as the whole record does:
    it keeps the members that their dynamic reads project and the fields that say when each is a
    member, and the formulas of occurrences with their starts and finishes."""
    example = EXAMPLES[name]()
    keys = tuple(sorted({item.key for item in example.expected if isinstance(item, At)}, key=str))
    times = sorted({float(item.t) for item in example.expected if isinstance(item, At)})
    request = example.configuration.request
    whole = run(example.program, example.configuration)
    some = run(example.program, Configuration(Request(request.horizon, everything=False, keys=keys)))
    assert len(some.histories) < len(whole.histories)
    found = [reading.values for reading in read(some, example.program, list(keys), times)]
    assert found == [reading.values for reading in read(whole, example.program, list(keys), times)]


def test_an_endpoint_of_an_occurrences_own_store_limits_and_ranks_its_flows():
    """A delivery moves 6 L into its own batch, whose outflow is capped at 3 L/h and ranks `second`
    first; two pipes each ask 2 L/h: `second` takes 2 and `first` the 1 left, so the batch is empty at
    2 h, with 2 L in a and 4 L in b."""
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        value('a', 'L', 0),
        value('b', 'L', 0),
        event(
            'deliver',
            value(
                'batch',
                'L',
                0,
                lower=0,
                outflow=endpoint(capacity=q(3, 'L/h'), allocation=priority(local.second)),
            ),
            flow('first', local.batch, this.a, request=q(2, 'L/h')),
            flow('second', local.batch, this.b, request=q(2, 'L/h')),
            value('total', 'L/h', formula(local.batch.outflow.actual_rate)),
            after(q(0, 'h'), move(q(6, 'L'), this.water, local.batch)),
            until(local.batch <= q(0, 'L')),
        ),
    )
    b.setup(start(tank.deliver))
    source = b.finish()
    record = run(source, Configuration(Request(3)))
    assert record.failure is None
    paths = [
        'tank.deliver#0.batch',
        'tank.deliver#0.first.actual_rate',
        'tank.deliver#0.second.actual_rate',
        'tank.deliver#0.total',
        'tank.a',
        'tank.b',
    ]
    found = [reading.values for reading in read(record, source, paths, [1, 3])]
    assert found == [(3, 0), (1, 0), (2, 0), (3, 0), (1, 2), (2, 4)]
    assert [entry.t for entry in record.entries('finish')] == [2]


def test_a_stage_gives_an_endpoint_a_new_allocation():
    """A reservoir capped at 10 L/h serves a (8 L/h) first; at 1 h a stage ranks b (12 L/h) first, and
    at 2 h shares proportionally: a gets 8, 0 and 4 L/h in turn, b 2, 10 and 6. The oracle agrees."""
    b = Builder(UNITS)
    a_pipe, b_pipe = named('a').pipe, named('b').pipe
    reservoir = b.entity(
        'reservoir',
        value(
            'water', 'L', 100, lower=0, outflow=endpoint(capacity=q(10, 'L/h'), allocation=priority(a_pipe))
        ),
        event('swap', after(q(1, 'h'), assign(this.water.outflow.allocation, priority(b_pipe)))),
        event('even', after(q(2, 'h'), assign(this.water.outflow.allocation, proportional()))),
    )
    b.entity('a', value('got', 'L', 0), flow('pipe', reservoir.water, this.got, request=q(8, 'L/h')))
    b.entity('b', value('got', 'L', 0), flow('pipe', reservoir.water, this.got, request=q(12, 'L/h')))
    b.setup(start(reservoir.swap), start(reservoir.even))
    source = b.finish()
    configuration = Configuration(Request(3))
    record = run(source, configuration)
    paths = ['a.pipe.actual_rate', 'b.pipe.actual_rate', 'a.got', 'b.got']
    found = [reading.values for reading in read(record, source, paths, [0.5, 1.5, 2.5, 3])]
    assert found == [(8, 0, 4, 4), (2, 10, 6, 6), (4, 8, 10, 12), (1, 7, 15, 18)]
    oracle, failed = run_of(source, configuration)
    assert failed is None
    assert [value_at(oracle, source, Key(name, ('got',)), 3) for name in ('a', 'b')] == [12, 18]
