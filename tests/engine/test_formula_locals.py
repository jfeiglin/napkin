"""An occurrence's `formula(...)` local is a retained calculation (spec.md:634, D14; D7 at spec.md:727).

Its entry gives a value to the parameters, the built-in fields, the plain locals and the plain
settings of its flows, in written order; a `formula(...)` local takes none there. It is evaluated
where something reads it, after the entry, so it may name a local declared below it, or a value that
has none yet (`since` of an event that has not started), and it fails nothing where nothing reads it.
When its occurrence finishes it keeps the value that it has then, or the reason why it has none, and
only a read of it fails the run.

The rule test: random events whose locals come in a random order (stored numbers, formulas of them,
of the parameter, of each other, and of `since` of an event that starts or not), started from the
setup, from a stage or from a firing, and read in a stage, through another formula or not at all;
both runs finish with the same values, or fail at the same time, the oracle (`tests/reference/`) in
exact fractions, the record holding each formula's value while its occurrence runs and its frozen
value or reason after. The same runs also stop at the reading stage and resume, in place and from the
saved state. The named cases are the review's (`audit/review-2cd1751`, R03), worked by hand.
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
    assign,
    event,
    flow,
    formula,
    local,
    named,
    param,
    q,
    reset_when,
    since,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.config import Configuration, Request
from napkin.program.record import Key, Unavailable
from tests.reference.errors import NotCovered, RunFailed
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
HORIZON = 4
TIMES = [Fraction(k, 2) for k in range(2 * HORIZON + 1)]
LOOK = 'plant.job.step[0]'  # the reading stage, where the runs that stop stop


def program(seed):
    """A random program (see the module): `plant.job(amount)` with its locals in a random order and
    a stage at 1 h that reads one of them (or none), `plant.other` that starts or not, and how `job`
    starts. Gives the program and the keys to compare."""
    rng = random.Random(seed)
    parts = [
        value('x', 'L', q(rng.choice([1, 3]), 'L')),
        value('double', 'L', formula(local.x * 2)),
        value('more', 'L', formula(local.double + local.amount)),
        value('waited', 'h', formula(since(named('plant').other))),
    ]
    rng.shuffle(parts)
    if rng.random() < 0.3:
        # A flow whose request names a later local, as the spec's own case does.
        parts.insert(
            rng.randint(0, len(parts)),
            flow('pipe', SOURCE, named('plant').water, request=formula(local.x / q(2, 'h'))),
        )
    read_one = rng.choice([local.double, local.more, local.waited, None])
    target = named('plant').when if read_one is local.waited else named('plant').seen
    body = [] if read_one is None else [assign(target, read_one)]
    how = rng.choice(['setup', 'stage', 'firing'])
    amount = q(rng.choice([0, 2]), 'L')
    starts = start(named('plant').job, amount)
    # A trigger starts its own event: the job's entry runs at a firing.
    fired = (
        [when(t >= q(1, 'h'), start(this.job, amount), reset=reset_when(False))] if how == 'firing' else []
    )
    job = event('job', param('amount', 'L'), *parts, after(q(1, 'h'), *body), *fired)
    other = event('other', after(q(0, 'h')))
    b = Builder(UNITS)
    plant = [
        value('water', 'L', 0, lower=0),
        value('seen', 'L', -1),
        value('when', 'h', -1),
        job,
        other,
        flow('drain', this.water, SINK, request=q(0, 'L/h')),
    ]
    if how == 'stage':
        plant.append(event('kick', after(q(rng.choice([0, 1]), 'h'), starts)))
    b.entity('plant', *plant)
    setup = [starts] if how == 'setup' else ([start(named('plant').kick)] if how == 'stage' else [])
    if rng.random() < 0.5:
        setup.append(start(named('plant').other))
    b.setup(*setup)
    keys = [Key('plant', (name,)) for name in ('seen', 'when', 'water')]
    keys += [Key('plant.job#0', (name,)) for name in ('double', 'more', 'waited')]
    return b.finish(), keys


def oracle_value(oracle, program, key, time):
    """What the oracle's record holds at a key, or Unavailable where it holds a reason."""
    try:
        found = value_at(oracle, program, key, time)
    except RunFailed as problem:
        return Unavailable(str(problem))
    return found


def records(program, configuration, stop):
    """The engine's records: straight through, or stopped at the reading stage and resumed in place and
    from the saved state."""
    if not stop:
        return [run(program, configuration)]
    made = Run(Plan.of(program, configuration), (Breakpoint(LOOK),))
    found = made.run()
    if not isinstance(found, Checkpoint):
        return [found]
    return [made.resume(), resume(program, loads(dumps(found)))]


def compare(seed, stop=False):
    program_, keys = program(seed)
    configuration = Configuration(Request(HORIZON))
    try:
        oracle, failed = run_of(program_, configuration)
    except NotCovered:
        return
    for record in records(program_, configuration, stop):
        message = None if record.failure is None else record.failure.detail('message')
        if failed is not None:
            assert message is not None and record.failure.t == pytest.approx(float(oracle.view.t)), (
                seed,
                str(failed),
                message,
            )
            horizon = oracle.view.t - Fraction(1, 10**9)
        else:
            assert message is None, (seed, message)
            horizon = Fraction(HORIZON)
        for key in keys:
            times = [time for time in TIMES if time < horizon]
            found = read(record, program_, [key], [float(time) for time in times])[0].values
            for time, number in zip(times, found):
                expected = oracle_value(oracle, program_, key, time)
                if isinstance(expected, Unavailable) or isinstance(number, Unavailable):
                    # Before the occurrence starts both have none; after it, the same reason or none.
                    assert isinstance(expected, Unavailable) == isinstance(number, Unavailable), (
                        seed,
                        str(key),
                        float(time),
                        number,
                        expected,
                    )
                    continue
                assert number == pytest.approx(float(expected), rel=1e-9, abs=1e-9), (
                    seed,
                    str(key),
                    float(time),
                )


@pytest.mark.parametrize('seed', range(120))
def test_an_occurrence_s_formula_locals_are_read_where_they_are_read(seed):
    compare(seed)


@pytest.mark.parametrize('seed', range(60))
def test_a_run_stopped_at_the_reading_stage_reads_them_so_too_in_place_and_resumed(seed):
    compare(seed, stop=True)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(120, 1120))
def test_more_formula_locals(seed):
    compare(seed)
    compare(seed, stop=True)


# ---- the review's cases (R03), worked by hand -------------------------------------------------------


def plant(*job_parts, starts=True, extra=()):
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('water', 'L', 0, lower=0),
        value('seen', 'L', -1),
        event('job', *job_parts),
        event('other', after(q(0, 'h'))),
        *extra,
    )
    if starts:
        b.setup(start(named('plant').job))
    program_ = b.finish()
    return program_, run(program_, Configuration(Request(3)))


def test_a_formula_local_may_name_a_local_below_it():
    """`f = formula(x * 2)` above `x: L = 3 L`, read at 1 h: 6 L (on 2cd1751 the run failed at 0 h,
    'plant.job#0.x has no value yet')."""
    program_, record = plant(
        value('f', 'L', formula(local.x * 2)),
        value('x', 'L', q(3, 'L')),
        after(q(1, 'h'), assign(named('plant').seen, local.f)),
    )
    assert record.failure is None, record.failure
    assert read(record, program_, ['plant.seen'], [1, 2])[0].values == (6.0, 6.0)


def test_a_formula_local_that_nothing_reads_fails_nothing_and_keeps_its_reason():
    """`g = formula(since(this.other))`, `other` never started: the run finishes, and g is
    unavailable after the finish at 1 h with the reason, `since` of an event that has not started (on
    2cd1751 the run failed at 0 h)."""
    program_, record = plant(value('g', 'h', formula(since(named('plant').other))), after(q(1, 'h')))
    assert record.failure is None, record.failure
    (found,) = read(record, program_, [Key('plant.job#0', ('g',))], [2])[0].values
    assert isinstance(found, Unavailable) and 'other' in found.reason


def test_a_read_of_a_formula_local_that_has_no_value_fails_the_run_there():
    """The same g read at 1 h, by a stage: the run fails there, as a read of it."""
    _, record = plant(
        value('g', 'h', formula(since(named('plant').other))),
        after(q(1, 'h'), assign(named('plant').seen, q(1, 'L') * local.g / q(1, 'h'))),
    )
    assert record.failure is not None and record.failure.t == 1


def test_a_flow_s_request_that_names_a_later_local_runs_as_before():
    """The spec's own case: `request = formula(left / (2 h))` with `left: L = 4 L` below: 2 L at 1 h."""
    program_, record = plant(
        flow('pipe', SOURCE, named('plant').water, request=formula(local.left / q(2, 'h'))),
        value('left', 'L', q(4, 'L')),
        after(q(1, 'h')),
    )
    assert record.failure is None
    assert read(record, program_, ['plant.water'], [1])[0].values == (pytest.approx(2.0),)
