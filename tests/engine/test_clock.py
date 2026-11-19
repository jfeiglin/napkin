"""The one rule for when something is due (re-audit 04, `briefs/audit2.md` part B): a schedule
reached by any sum of durations behaves as the same schedule written directly.

A trigger that first fired at 0.1 h and reset after 0.1 h fired its third time at
0.30000000000000004 h, and not at all at a 0.3 h horizon: its times were sums of floats, while stages
met the horizon by a tolerance of their own. The clock (`moment.Clock`) builds every time from a
duration in exact arithmetic and decides what is due by one comparison, on every path. The rule,
on random sums of decimal durations in hours and in days:

- a chain of stages commits at the sums, in the round and the order of stages written directly at
  them (D5: one round, in the order in which their occurrences were made), and reads the same at
  each of those times, the last of them the horizon;
- a trigger that resets after a duration fires at the sums, the last at the horizon;
- `since`, `elapsed` and a gate change at the sum of the time from which they count and the
  duration, as a trigger on that time written directly does;
- two occurrences started at one time by a chain and by a direct schedule start in one moment and
  one round, and `.occurrences.at(t)` takes the one created later.

The expected times are the sums in exact fractions, as a model writes them, never a run's output.
"""

from __future__ import annotations

import itertools
import random
from fractions import Fraction

import pytest

from napkin.engine.timeline import read, run
from napkin.program.build import (
    Builder,
    add,
    after,
    assign,
    count,
    elapsed,
    event,
    formula,
    param,
    q,
    reset_after,
    reset_when,
    since,
    start,
    t,
    this,
    until,
    value,
    when,
)
from napkin.program.config import Configuration, Request

UNITS = {
    'h': {'time': 1},
    'day': ({'time': 1}, 24),
    'min': ({'time': 1}, Fraction(1, 60)),
    'L': {'volume': 1},
}


def durations(rng, n):
    """n random decimal durations, each (the quantity that the model writes, its value in hours): a
    tenth of a day up to two days, or hours in tenths, twentieths, hundredths or quarters."""
    found = []
    for _ in range(n):
        if rng.random() < 0.3:
            days = Fraction(rng.randint(1, 20), 10)
            found.append((q(float(days), 'day'), days * 24))
        else:
            hours = Fraction(rng.randint(1, 40), rng.choice([10, 20, 100, 4]))
            found.append((q(float(hours), 'h'), hours))
    return found


def at(record, program, path, times):
    (reading,) = read(record, program, [path], [float(time) for time in times])
    return list(reading.values)


# ---- stages ------------------------------------------------------------------------------------


def stages(seed):
    """`chain` waits each duration in turn; `direct{k}` waits the k-th sum, written as one number of
    hours. The setup starts the chain first. Each stage adds to its counter and sets `last`."""
    rng = random.Random(seed)
    steps = durations(rng, rng.randint(2, 8))
    sums = list(itertools.accumulate(hours for _, hours in steps))
    b = Builder(UNITS)
    directs = [
        event(f'direct{k}', after(q(float(total), 'h'), add(this.direct, 1), assign(this.last, 2)))
        for k, total in enumerate(sums)
    ]
    crew = b.entity(
        'crew',
        value('chained', '', 0),
        value('direct', '', 0),
        value('last', '', 0),
        event('chain', *[after(delay, add(this.chained, 1), assign(this.last, 1)) for delay, _ in steps]),
        *directs,
    )
    b.setup(start(crew.chain), *[start(getattr(crew, f'direct{k}')) for k in range(len(sums))])
    return b.finish(), Configuration(Request(float(sums[-1]))), sums


@pytest.mark.parametrize('seed', range(40))
def test_a_chain_of_stages_commits_where_the_same_stages_written_directly_do(seed):
    program, configuration, sums = stages(seed)
    record = run(program, configuration)
    assert record.failure is None
    commits = {}
    for entry in record.entries('commit'):
        commits.setdefault(entry.owner.split('#')[0], []).append(entry)
    chained = commits['crew.chain']
    assert [entry.t for entry in chained] == [float(total) for total in sums]
    for k in range(len(sums)):
        (direct,) = commits[f'crew.direct{k}']
        assert direct.t == chained[k].t and direct.round == chained[k].round
        assert record.trace.index(chained[k]) < record.trace.index(direct)  # made first, commits first
    times = list(sums)
    counts = list(range(1, len(sums) + 1))
    assert at(record, program, 'crew.chained', times) == counts
    assert at(record, program, 'crew.direct', times) == counts
    assert at(record, program, 'crew.last', times) == [2] * len(sums)


# ---- resets ------------------------------------------------------------------------------------


@pytest.mark.parametrize('seed', range(40))
def test_a_trigger_that_resets_after_a_duration_fires_at_its_sums_the_last_at_the_horizon(seed):
    """`when t >= a` with `reset after d` fires at a, a + d, ..., a + (n - 1) d; the horizon is the
    last, which the trigger meets (the horizon is an inclusive cutoff)."""
    rng = random.Random(1000 + seed)
    (first, a), (period, d) = durations(rng, 2)
    times = [a + k * d for k in range(rng.randint(2, 15))]
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('ticks', '', 0),
        event(
            'tick',
            when(t >= first, start(this.tick), reset=reset_after(period)),
            after(q(0, 'h'), add(this.ticks, 1)),
        ),
    )
    program = b.finish()
    record = run(program, Configuration(Request(float(times[-1]))))
    assert record.failure is None
    assert [entry.t for entry in record.entries('fire')] == [float(time) for time in times]
    assert at(record, program, 'plant.ticks', [times[-1]]) == [len(times)]


# ---- since, elapsed and a gate -------------------------------------------------------------------


@pytest.mark.parametrize('seed', range(30))
def test_since_elapsed_and_a_gate_change_at_the_sum_of_their_start_and_their_duration(seed):
    """A chain reaches S: it sets `mark` and starts `ping`. `since(ping) >= D`, `elapsed(mark) >= D`
    and a gate on `since(ping) >= D` act at S + D, as a trigger on `t >= S + D` written directly."""
    rng = random.Random(2000 + seed)
    steps = durations(rng, rng.randint(1, 4))
    wait, length = durations(rng, 1)[0]
    reached = sum(hours for _, hours in steps)
    expected = float(reached + length)
    started = (count(this.ping.occurrences) > 0) & (since(this.ping) >= wait)
    once = reset_when(False)
    b = Builder(UNITS)
    crew = b.entity(
        'crew',
        value('mark', '', 0),
        *[value(name, 'h', -1) for name in ('since_at', 'elapsed_at', 'gate_at', 'direct_at')],
        event(
            'go',
            *[after(delay) for delay, _ in steps[:-1]],
            after(steps[-1][0], assign(this.mark, 1), start(this.ping)),
        ),
        event('ping'),
        event(
            'on_since',
            when(started, start(this.on_since), reset=once),
            after(q(0, 'h'), assign(this.since_at, t)),
        ),
        event(
            'on_elapsed',
            when((this.mark > 0) & (elapsed(this.mark) >= wait), start(this.on_elapsed), reset=once),
            after(q(0, 'h'), assign(this.elapsed_at, t)),
        ),
        event('gated', until(started), after(q(0, 'h'), assign(this.gate_at, t))),
        event(
            'on_time',
            when(t >= q(expected, 'h'), start(this.on_time), reset=once),
            after(q(0, 'h'), assign(this.direct_at, t)),
        ),
    )
    b.setup(start(crew.go), start(crew.gated))
    program = b.finish()
    record = run(program, Configuration(Request(expected + 1)))
    assert record.failure is None
    found = [
        at(record, program, f'crew.{name}', [expected + 1])[0]
        for name in ('since_at', 'elapsed_at', 'gate_at')
    ]
    assert found == [expected] * 3
    assert at(record, program, 'crew.direct_at', [expected + 1]) == [expected]
    rounds = {
        (entry.t, entry.round)
        for entry in record.entries('commit')
        if entry.part.endswith('step[0]') and entry.t == expected
    }
    assert len({round_ for _, round_ in rounds}) <= 2  # the firings' stages at S + D: no moment between


# ---- occurrences started together ----------------------------------------------------------------


@pytest.mark.parametrize('seed', range(30))
def test_occurrences_started_together_by_a_sum_and_directly_are_one_moments(seed):
    """At S, the chain starts `mark(1)` and a stage written at S starts `mark(2)`: one moment, one
    round, both count, and `.occurrences.at(t)` takes the later-created, 2."""
    rng = random.Random(3000 + seed)
    steps = durations(rng, rng.randint(2, 6))
    reached = float(sum(hours for _, hours in steps))
    b = Builder(UNITS)
    crew = b.entity(
        'crew',
        value('newest', '', formula(this.mark.occurrences.at(t).which)),
        value('marks', '', formula(count(this.mark.occurrences))),
        event('mark', param('which', '')),
        event('chain', *[after(delay) for delay, _ in steps[:-1]], after(steps[-1][0], start(this.mark, 1))),
        event('direct', after(q(reached, 'h'), start(this.mark, 2))),
    )
    b.setup(start(crew.chain), start(crew.direct))
    program = b.finish()
    record = run(program, Configuration(Request(reached + 1)))
    assert record.failure is None
    starts = record.entries('start', 'crew.mark')
    assert [(entry.t, entry.round) for entry in starts] == [(reached, starts[0].round)] * 2
    assert at(record, program, 'crew.marks', [reached]) == [2]
    assert at(record, program, 'crew.newest', [reached]) == [2]


# ---- the re-audit's case and its variants ----------------------------------------------------------


def clock_trigger(horizon, first='0.1', period=(0.1, 'h')):
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('ticks', '', 0),
        event(
            'tick',
            when(t >= q(float(first), 'h'), start(this.tick), reset=reset_after(q(*period))),
            after(q(0, 'h'), add(this.ticks, 1)),
        ),
    )
    program = b.finish()
    return program, run(program, Configuration(Request(horizon)))


def test_a_trigger_that_resets_after_a_tenth_of_an_hour_fires_three_times_by_a_horizon_of_three_tenths():
    """Re-audit 04: it fires at 0.1 h, 0.2 h and 0.3 h, the horizon."""
    program, record = clock_trigger(0.3)
    assert [entry.t for entry in record.entries('fire')] == [0.1, 0.2, 0.3]
    assert at(record, program, 'plant.ticks', [0.3]) == [3]


def test_with_a_longer_horizon_its_tenth_firing_is_at_one_hour_exactly():
    """Its third firing is at 0.3 h, not 0.30000000000000004 h, and the tenth at 1 h."""
    _, record = clock_trigger(1)
    assert [entry.t for entry in record.entries('fire')] == [k / 10 for k in range(1, 11)]


def test_a_tenth_of_a_day_is_the_moment_of_two_point_four_hours():
    """`after 0.1 day` is due at 2.4 h, the float of 2.4, at the moment and in the round of `after
    2.4 h`: a duration's expression is exact (0.1 x 24 in floats is 2.4000000000000004)."""
    b = Builder(UNITS)
    b.entity(
        'crew',
        value('n', '', 0),
        event('days', after(q(0.1, 'day'), add(this.n, 1))),
        event('hours', after(q(2.4, 'h'), add(this.n, 10))),
    )
    b.setup(start(named_of('crew').days), start(named_of('crew').hours))
    program = b.finish()
    record = run(program, Configuration(Request(2.4)))
    commits = [(entry.t, entry.round) for entry in record.entries('commit')]
    assert commits == [(2.4, commits[0][1])] * 2
    assert at(record, program, 'crew.n', [2.4]) == [11]


def test_three_resets_of_twenty_minutes_are_the_moment_of_one_hour():
    """A third of an hour has no decimal: three of them are due at the moment of 1 h, within the
    time tolerance, and the trigger written at 1 h fires in the same round after them."""
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('ticks', '', 0),
        value('hour', '', 0),
        event(
            'tick',
            when(t >= q(0, 'h'), start(this.tick), reset=reset_after(q(20, 'min'))),
            after(q(0, 'h'), add(this.ticks, 1)),
        ),
        event(
            'ring',
            when(t >= q(1, 'h'), start(this.ring), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.hour, this.ticks)),
        ),
    )
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    fires = record.entries('fire')
    assert [entry.part for entry in fires] == ['plant.tick.when[0]'] * 4 + ['plant.ring.when[0]']
    assert fires[3].t == pytest.approx(1, abs=1e-12) and fires[4].t == fires[3].t
    assert at(record, program, 'plant.hour', [1]) == [4]


def named_of(name):
    from napkin.program.build import named

    return named(name)
