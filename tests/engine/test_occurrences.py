"""Small random programs with events, against the oracle (`tests/reference/`).

Each case has a few tanks: stores with bounds, entity flows that fill, drain or pass water between
them at constant requests, sometimes an outflow capacity, and a counter. Their events start from the
setup and from triggers: a clock (`when t >= T`, with `reset after P` or once), a level on a tank
(`when water <= L` or `>= H`, with a reset or none). An event's occurrence may own a pipe from its
tank (to the outside or to another tank), whose flow joins the network at its start and leaves at
its finish; own a batch that a move fills and a flow empties; wait a delay or at a gate on a level;
and run stages that add to its tank, take from it, move water between tanks and count. Requests and levels are whole numbers and halves, and rates are
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
from napkin.engine.timeline import Plan
from napkin.engine.timeline.record import remember
from napkin.program.build import (
    BOOL,
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    endpoint,
    event,
    flow,
    local,
    move,
    named,
    q,
    reset_after,
    reset_when,
    start,
    subtract,
    t,
    this,
    until,
    value,
    when,
)
from napkin.program.config import Configuration, Limits, Request
from napkin.program.record import Key
from tests.program.examples import EXAMPLES, At
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of, traced, value_at

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
    count = rng.randint(1, 3)
    tanks = [f't{k}' for k in range(count)]
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
        elif kind == 'pass' and count > 1:
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
        steps = [after(delay, *body)]
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
    for key in keys:
        found = read(record, source, [key], [float(time) for time in times])[0].values
        for time, number in zip(times, found):
            expected = float(value_at(oracle, source, key, time))
            assert number == pytest.approx(expected, rel=1e-9, abs=1e-9), (seed, str(key), float(time))


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
    # The reader keeps the plan of the last run: a plan of the program alone takes its place.
    remember(Plan.of(example.program, Configuration(Request(0))))
    again = [reading.values for reading in read(record, example.program, keys, times)]
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
