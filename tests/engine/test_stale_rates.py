"""A round reads the rates of the last re-share (PLAN, change 27).

Small seeded networks change requests, capacities, allocations, levels and flow membership.
Stages read a rate directly or in a formula, before and after re-sharing. An edit before the
reading stage is resumed in place and from a checkpoint. The exact interpreter checks the
values along both paths. The named examples below use hand-worked amounts and rates.
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
    endpoint,
    event,
    flow,
    formula,
    legs,
    move,
    named,
    priority,
    proportional,
    q,
    reset_when,
    route,
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
from tests.reference.from_program import run_of, values_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
HORIZON = 4
TIMES = [Fraction(k, 2) for k in range(2 * HORIZON + 1)]
STORES = {  # start, lower, upper
    'stocked': (6, 0, 100),
    'empty': (0, 0, 100),
    'full': (10, 0, 10),
    'junction': (0, 0, 0),
    'small': (2, 0, 8),
}
LOOK = 'ops.look.step[0]'  # the reading stage, where the runs with an edit stop
BEFORE_SETUP = 'is read before'  # a result has no value until the setup commits
# Where local sharing has no answer, the oracle has none (`NotCovered`) and the engine stops, naming
# the stores; both find it where the flows first settle, after the setup's commit, from the state that
# the setup leaves (`run.Run.prepare`).
NO_ANSWER = ('ring of stores', 'a request at an endpoint that the route')


def rate(number):
    return None if number is None else q(number, 'L/h')


def network(seed):
    """A random program (see the module): stores `s<k>.water`, flows `f<k>.pipe`, a route `r0.link`,
    a flow with legs `g0.restore`, and the operator `ops`, whose events change and read them. Gives
    the program, the keys to compare, and an edit of a store (its key and a level within its
    bounds)."""
    rng = random.Random(seed)
    count = rng.randint(1, 3)
    kinds = [rng.choice(list(STORES)) for _ in range(count)]
    ends = list(range(count))

    def directed():
        source = rng.choice([None, *ends])
        sink = rng.choice([s for s in [None, *ends] if s != source or s is None])
        if source is None and sink is None and rng.random() < 0.7:
            sink = rng.choice(ends)  # a flow from SOURCE to SINK now and then
        return source, sink, rng.choice([0, Fraction(1, 2), 1, 2, 4]), rng.choice([None, None, 1, 2, 4])

    flows = [directed() for _ in range(rng.randint(1, 4))]
    links = []
    stocked = [s for s in ends if kinds[s] == 'stocked']
    if len(stocked) >= 2 and rng.random() < 0.5:
        # A route between two stocked stores: where one end of a route is full or a `[0, 0]`
        # junction, local sharing of the oracle and of the engine part, change 25 or not (For the
        # main session, b1/audit3-t).
        first, second = rng.sample(stocked, 2)
        links.append((first, second, rng.choice([-2, -1, 1, 2]), rng.choice([None, 1, 4])))
    restores = [[directed(), directed()] for _ in range(rng.random() < 0.25)]
    incident = {(s, side): [] for s in ends for side in ('outflow', 'inflow')}

    def meets(source, sink, path):
        if source is not None:
            incident[(source, 'outflow')].append(path)
        if sink is not None:
            incident[(sink, 'inflow')].append(path)

    for k, (source, sink, _, _) in enumerate(flows):
        meets(source, sink, named(f'f{k}').pipe)
    for k, (first, second, _, _) in enumerate(links):
        meets(first, second, named(f'r{k}').link.forward)
        meets(second, first, named(f'r{k}').link.backward)
    for k, pair in enumerate(restores):
        for name, (source, sink, _, _) in zip('ab', pair):
            meets(source, sink, getattr(named(f'g{k}').restore, name))
    # The store that the pipe of an occurrence of `deliver` drains: its outflow has a flow to read
    # (None: no flow that a priority names).
    delivered = rng.choice(ends)
    incident[(delivered, 'outflow')].append(None)
    b = Builder(UNITS)
    for s, kind in enumerate(kinds):
        level, lower, upper = STORES[kind]
        mine = [path for path in incident[(s, 'outflow')] if path is not None]
        # Every outflow is declared, so that a stage may set its allocation (one that the program
        # declares nowhere has no request in a run whose flows join: for the main session).
        allocation, capacity = proportional(), None
        if rng.random() < 0.4:
            if len(mine) >= 2 and rng.random() < 0.6:
                allocation = priority(*rng.sample(mine, rng.randint(1, len(mine))))
            capacity = rng.choice([None, q(1, 'L/h'), q(3, 'L/h')])
        outflow = endpoint(capacity=capacity, allocation=allocation)
        b.entity(f's{s}', value('water', 'L', level, lower=lower, upper=upper, outflow=outflow))

    def end(s, outside):
        return outside if s is None else named(f's{s}').water

    for k, (source, sink, request, capacity) in enumerate(flows):
        unit = 'L/h' if source is None and sink is None else ''
        b.entity(
            f'f{k}',
            flow(
                'pipe',
                end(source, SOURCE),
                end(sink, SINK),
                request=rate(request),
                capacity=rate(capacity),
                unit=unit,
            ),
        )
    for k, (first, second, request, capacity) in enumerate(links):
        b.entity(
            f'r{k}',
            route(
                'link', end(first, None), end(second, None), request=rate(request), capacity=rate(capacity)
            ),
        )
    for k, pair in enumerate(restores):
        parts = []
        for name, (source, sink, request, capacity) in zip('ab', pair):
            unit = 'L/h' if source is None and sink is None else ''
            parts.append(
                flow(
                    name,
                    end(source, SOURCE),
                    end(sink, SINK),
                    request=rate(request),
                    capacity=rate(capacity),
                    unit=unit,
                )
            )
        b.entity(f'g{k}', legs('restore', *parts))

    # What a stage reads: (a rate, whether it is a fraction).
    reads = [(named(f'f{k}').pipe.actual_rate, False) for k in range(len(flows))]
    for k in range(len(links)):
        reads += [(named(f'r{k}').link.actual_rate, False), (named(f'r{k}').link.forward.actual_rate, False)]
    for k in range(len(restores)):
        reads += [
            (named(f'g{k}').restore.served_fraction, True),
            (named(f'g{k}').restore.a.actual_rate, False),
        ]
    for s in ends:
        for side in ('outflow', 'inflow'):
            if incident[(s, side)]:
                reads.append((getattr(named(f's{s}').water, side).actual_rate, False))
    early = rng.random() < 0.5  # an occurrence of `deliver` from the setup, whose pipe leaves later
    if early:
        reads.append((named('ops').deliver.occurrences.at(t).pipe.actual_rate, False))
        reads.append((named('ops').deliver.occurrences.at(t).tap.actual_rate, False))

    # What a stage changes.
    changes = [start(this.deliver)]
    for k, (_, _, _, capacity) in enumerate(flows):
        changes.append(assign(named(f'f{k}').pipe.request, rate(rng.choice([0, 1, 3]))))
        if capacity is not None:
            changes.append(assign(named(f'f{k}').pipe.capacity, rate(rng.choice([0, Fraction(1, 2), 2]))))
    for k in range(len(links)):
        changes.append(assign(named(f'r{k}').link.request, rate(rng.choice([-1, 3]))))
    for k in range(len(restores)):
        changes.append(assign(named(f'g{k}').restore.b.request, rate(rng.choice([0, 1, 3]))))
    for s, kind in enumerate(kinds):
        _, lower, upper = STORES[kind]
        changes.append(
            assign(named(f's{s}').water, q(rng.choice([lower, Fraction(lower + upper, 2), upper]), 'L'))
        )
        mine = [path for path in incident[(s, 'outflow')] if path is not None]
        if mine:
            changes.append(assign(named(f's{s}').water.outflow.allocation, priority(rng.choice(mine))))
        other = rng.choice(ends)
        if other != s:
            changes.append(
                move(q(rng.choice([Fraction(1, 2), 2]), 'L'), named(f's{s}').water, named(f's{other}').water)
            )

    picked, fraction = rng.choice(reads)
    unit = '' if fraction else 'L/h'
    target = this.share if fraction else this.seen
    looked = this.twice if rng.random() < 0.3 else picked  # through a formula, or directly
    # `change` writes at its time, and may read in the same stage; `look` reads at its time, and may
    # read again in the next round of that time.
    body = rng.sample(changes, rng.randint(1, 2))
    if rng.random() < 0.3:
        body.append(assign(target, looked))
    looking = [after(q(rng.choice([1, 2, 3]), 'h'), assign(target, looked))]
    if rng.random() < 0.6:
        looking.append(after(q(0, 'h'), assign(this.again, picked)))
    pipe = flow('pipe', named(f's{delivered}').water, SINK, request=rate(rng.choice([1, 2])))
    tap = flow('tap', SOURCE, SINK, request=rate(rng.choice([1, 2])), unit='L/h')  # stops with it
    # A firing in the conditions of a round starts `deliver`: its pipe joins its store before the
    # next round's stages, which the flows settle after.
    fired = [when(t >= q(rng.choice([1, 2, 3]), 'h'), start(this.deliver), reset=reset_when(False))]
    fired = fired if rng.random() < 0.3 else []
    b.entity(
        'ops',
        value('seen', 'L/h', -1),
        value('share', '', -1),
        value('again', unit, -1),
        value('twice', unit, formula(picked * 2)),
        event('change', after(q(rng.choice([1, 2, 3]), 'h'), *body)),
        event('look', *looking),
        event('deliver', pipe, tap, after(q(rng.choice([1, 2]), 'h')), *fired),
    )
    order = [start(named('ops').change), start(named('ops').look)]
    if early:
        order.append(start(named('ops').deliver))
    rng.shuffle(order)
    if rng.random() < 0.1:
        order.append(assign(named('ops').again, picked))  # a read in the setup
    b.setup(*order)
    keys = [Key(f's{s}', ('water',)) for s in ends] + [
        Key('ops', (name,)) for name in ('seen', 'share', 'again')
    ]
    edited = rng.choice(ends)
    _, lower, upper = STORES[kinds[edited]]
    return b.finish(), keys, (Key(f's{edited}', ('water',)), rng.choice([lower, upper]))


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
    exact = None
    for record in engine_records(program, configuration, change if edit else None):
        message = None if record.failure is None else record.failure.detail('message')
        if message is not None and record.failure.t == 0 and any(reason in message for reason in NO_ANSWER):
            continue
        if oracle is None:  # the setup fails
            assert message is not None and record.failure.t == 0, (seed, str(failed))
            continue
        if failed is not None:
            assert message is not None, (seed, str(failed))
            assert record.failure.t == pytest.approx(float(oracle.view.t)), (seed, str(failed), message)
            assert (BEFORE_SETUP in message) == (BEFORE_SETUP in str(failed)), (seed, str(failed), message)
            if BEFORE_SETUP in message:
                assert oracle.view.t == 0, (seed, message)
            horizon = oracle.view.t - Fraction(1, 10**9)  # what happens at the failure is not compared
        else:
            assert message is None, (seed, message)
            horizon = Fraction(HORIZON)
        times = [time for time in TIMES if time < horizon]
        if exact is None:
            exact = values_at(oracle, program, keys, times)
        rows = read(record, program, keys, list(map(float, times)))
        for key, row in zip(keys, rows, strict=True):
            for time, number, expected in zip(times, row.values, exact[key], strict=True):
                assert number == pytest.approx(float(expected), rel=1e-9, abs=1e-9), (
                    seed,
                    str(key),
                    float(time),
                )


@pytest.mark.parametrize('seed', range(200))
def test_rates_through_the_round_agree_with_the_oracle(seed):
    compare(seed)


@pytest.mark.parametrize('seed', range(200))
def test_an_edit_at_a_stop_before_the_read_is_a_change_of_the_round_in_place_and_resumed(seed):
    compare(seed, edit=True)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(200, 2200))
def test_more_rates_through_the_round_agree_with_the_oracle(seed):
    compare(seed)
    compare(seed, edit=True)


# ---- the named cases, worked by hand -----------------------------------------------------------------


def tank(*stages, setup=(), request=3, extra=()):
    """A tank of 8 L in [0, 20] with a pipe to the outside at `request` L/h, and an operator whose
    event `look` runs `stages` (each an `after`): the program and its record over 6 h."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 8, lower=0, upper=20),
        flow('pipe', this.water, SINK, request=rate(request)),
    )
    b.entity(
        'ops',
        value('seen', 'L/h', -1),
        value('twice', 'L/h', formula(named('tank').pipe.actual_rate * 2)),
        event('look', *stages),
        *extra,
    )
    b.setup(start(named('ops').look), *setup)
    program = b.finish()
    return program, run(program, Configuration(Request(6)))


def seen(program, record, at):
    return read(record, program, [Key('ops', ('seen',))], [at])[0].values[0]


def failure(record):
    """(the time of the failure of a run, its message), or (None, '') for a run that finished."""
    return (None, '') if record.failure is None else (record.failure.t, record.failure.detail('message'))


PIPE = named('tank').pipe


def test_a_rate_after_a_change_of_its_request_reads_as_the_round_began():
    program, record = tank(
        after(q(1, 'h'), assign(PIPE.request, q(2, 'L/h')), assign(this.seen, PIPE.actual_rate))
    )
    assert record.failure is None
    assert seen(program, record, 1) == 3


def test_a_formula_reads_the_same_published_rate():
    program, record = tank(after(q(1, 'h'), assign(PIPE.request, q(2, 'L/h')), assign(this.seen, this.twice)))
    assert record.failure is None
    assert seen(program, record, 1) == 6


def test_the_next_round_and_a_later_time_read_the_settled_rate():
    """The request falls to 2 L/h at 1 h: the next round of 1 h reads 2 L/h, and so does 2 h; with no
    change, 1 h reads the 3 L/h that settled at 0 h."""
    program, record = tank(
        after(q(1, 'h'), assign(PIPE.request, q(2, 'L/h'))),
        after(q(0, 'h'), assign(this.seen, PIPE.actual_rate)),
    )
    assert failure(record)[0] is None and seen(program, record, 1) == 2
    program, record = tank(
        after(q(1, 'h'), assign(PIPE.request, q(2, 'L/h'))), after(q(1, 'h'), assign(this.seen, this.twice))
    )
    assert failure(record)[0] is None and seen(program, record, 2) == 4
    program, record = tank(after(q(1, 'h'), assign(this.seen, PIPE.actual_rate)))
    assert failure(record)[0] is None and seen(program, record, 1) == 3


def test_a_later_stage_of_the_round_reads_the_same_rate():
    """At 1 h the pipe still reads 3 L/h in either order of the closing and reading stages."""
    cut = event('cut', after(q(1, 'h'), assign(PIPE.request, q(0, 'L/h'))))
    reading = after(q(1, 'h'), assign(this.seen, PIPE.actual_rate))
    program, record = tank(reading, setup=(start(named('ops').cut),), extra=(cut,))
    assert failure(record)[0] is None and seen(program, record, 1) == 3
    b = Builder(UNITS)
    b.entity(
        'tank', value('water', 'L', 8, lower=0, upper=20), flow('pipe', this.water, SINK, request=q(3, 'L/h'))
    )
    b.entity('ops', value('seen', 'L/h', -1), cut, event('look', reading))
    b.setup(start(named('ops').cut), start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert record.failure is None
    assert seen(program, record, 1) == 3


def test_a_store_that_meets_its_bound_shares_again_after_the_stages():
    """8 L at 2 L/h empties at 4 h. The first stage reads 2 L/h and the next round reads 0."""
    program, record = tank(after(q(4, 'h'), assign(this.seen, PIPE.actual_rate)), request=2)
    assert record.failure is None and seen(program, record, 4) == 2
    program, record = tank(after(q(4, 'h')), after(q(0, 'h'), assign(this.seen, PIPE.actual_rate)), request=2)
    assert record.failure is None and seen(program, record, 4) == 0


def test_a_rate_read_in_the_setup_is_read_before_the_flows_first_settle():
    b = Builder(UNITS)
    b.entity(
        'tank', value('water', 'L', 8, lower=0, upper=20), flow('pipe', this.water, SINK, request=q(3, 'L/h'))
    )
    b.entity('ops', value('seen', 'L/h', -1))
    b.setup(assign(named('ops').seen, PIPE.actual_rate))
    record = run(b.finish(), Configuration(Request(1)))
    at, message = failure(record)
    assert at == 0 and 'tank.pipe.actual_rate is read before' in message and 'setup' in message


def deliveries(*look, fired=None):
    """A tank of 8 L whose outflow carries at most 2 L/h, shared by `main` (2 L/h) and the pipe of an
    occurrence of `deliver` (2 L/h), started in the setup and finished at 1 h, started at 1 h by
    `go`, or by a firing (`fired`); `look` reads at 1 h, after them."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 8, lower=0, upper=20, outflow=endpoint(capacity=q(2, 'L/h'))),
        flow('main', this.water, SINK, request=q(2, 'L/h')),
    )
    b.entity(
        'ops',
        value('seen', 'L/h', -1),
        event(
            'deliver',
            flow('pipe', named('tank').water, SINK, request=q(2, 'L/h')),
            after(q(1, 'h')),
            *([fired] if fired is not None else []),
        ),
        event('go', after(q(1, 'h'), start(this.deliver))),
        event('look', *look),
    )
    return b


def test_a_flow_that_leaves_and_its_neighbor_keep_their_round_rates():
    """At 1 h both pipes read their 1 L/h share. After re-sharing, main takes all 2 L/h."""
    occurrence = this.deliver.occurrences.at(t).pipe.actual_rate
    b = deliveries(after(q(1, 'h'), assign(this.seen, occurrence)))
    b.setup(start(named('ops').deliver), start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert failure(record)[0] is None and seen(program, record, 1) == 1
    b = deliveries(after(q(1, 'h'), assign(this.seen, named('tank').main.actual_rate)))
    b.setup(start(named('ops').deliver), start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert record.failure is None
    assert seen(program, record, 1) == 1
    b = deliveries(after(q(1, 'h')), after(q(0, 'h'), assign(this.seen, named('tank').main.actual_rate)))
    b.setup(start(named('ops').deliver), start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert failure(record)[0] is None and seen(program, record, 1) == 2


def test_a_flow_that_joins_reads_zero_until_its_first_share():
    occurrence = this.deliver.occurrences.at(t).pipe.actual_rate
    b = deliveries(after(q(1, 'h'), assign(this.seen, occurrence)))
    b.setup(start(named('ops').go), start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert record.failure is None
    assert seen(program, record, 1) == 0


def test_an_allocation_set_in_the_round_takes_effect_at_the_next_share():
    """With both pipes running, main gets 1 L/h in the writing stage and 2 L/h after it."""
    allocation = assign(named('tank').water.outflow.allocation, priority(named('tank').main))
    b = deliveries(
        after(q(0.5, 'h'), allocation), after(q(0, 'h'), assign(this.seen, named('tank').main.actual_rate))
    )
    b.setup(start(named('ops').deliver), start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert failure(record)[0] is None and seen(program, record, 0.5) == 2
    b = deliveries(after(q(0.5, 'h'), allocation, assign(this.seen, named('tank').main.actual_rate)))
    b.setup(start(named('ops').deliver), start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert record.failure is None
    assert seen(program, record, 0.5) == 1


def test_a_flow_from_source_to_sink_is_shared_again_after_the_stages_too():
    b = Builder(UNITS)
    b.entity('tap', flow('pipe', SOURCE, SINK, request=q(3, 'L/h'), unit='L/h'))
    b.entity(
        'ops',
        value('seen', 'L/h', -1),
        event(
            'look',
            after(
                q(1, 'h'),
                assign(named('tap').pipe.request, q(2, 'L/h')),
                assign(this.seen, named('tap').pipe.actual_rate),
            ),
        ),
    )
    b.setup(start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert record.failure is None
    assert seen(program, record, 1) == 3


def test_a_rate_that_follows_the_time_reads_at_the_current_time():
    """A request of t L/h at 2 h reads 2 L/h on either side of a capacity write in the stage."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 50, lower=0),
        flow('pipe', this.water, SINK, request=formula(t * q(1, 'L/h/h')), capacity=q(10, 'L/h')),
    )
    b.entity(
        'ops', value('seen', 'L/h', -1), event('look', after(q(2, 'h'), assign(this.seen, PIPE.actual_rate)))
    )
    b.setup(start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(3)))
    assert failure(record)[0] is None and seen(program, record, 2) == pytest.approx(2, abs=1e-9)
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 50, lower=0),
        flow('pipe', this.water, SINK, request=formula(t * q(1, 'L/h/h')), capacity=q(10, 'L/h')),
    )
    b.entity(
        'ops',
        value('seen', 'L/h', -1),
        event(
            'look', after(q(2, 'h'), assign(PIPE.capacity, q(1, 'L/h')), assign(this.seen, PIPE.actual_rate))
        ),
    )
    b.setup(start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(3)))
    assert record.failure is None
    assert seen(program, record, 2) == pytest.approx(2, abs=1e-9)


def test_a_rate_that_reads_another_sets_rate_keeps_its_share():
    """The meter follows the tank. Both shared 3 L/h before the operator cut the request."""
    b = Builder(UNITS)
    b.entity(
        'tank', value('water', 'L', 8, lower=0, upper=20), flow('pipe', this.water, SINK, request=q(3, 'L/h'))
    )
    b.entity(
        'meter',
        value('count', 'L', 0, lower=0),
        flow('feed', SOURCE, this.count, request=formula(PIPE.actual_rate)),
    )
    b.entity(
        'ops',
        value('seen', 'L/h', -1),
        event(
            'look',
            after(
                q(1, 'h'),
                assign(PIPE.request, q(2, 'L/h')),
                assign(this.seen, named('meter').feed.actual_rate),
            ),
        ),
    )
    b.setup(start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert record.failure is None
    assert seen(program, record, 1) == 3


def test_an_edit_at_a_stop_keeps_the_round_rate_in_place_and_in_a_fresh_process(tmp_path):
    """The operator reads 3 L/h after an edit, in place and from the saved stop."""
    program, _ = tank(after(q(1, 'h'), assign(this.seen, PIPE.actual_rate)))
    configuration = Configuration(Request(6))
    made = Run(Plan.of(program, configuration), (Breakpoint(LOOK),))
    stopped = made.run()
    assert isinstance(stopped, Checkpoint) and stopped.stop.t == 1
    edited = made.edit(Key('tank', ('water',)), 0)
    for record in (made.resume(), *in_a_fresh_process(program, [edited], tmp_path)):
        assert record.failure is None and seen(program, record, 1) == 3
    made = Run(Plan.of(program, configuration), (Breakpoint(LOOK),))
    made.run()
    record = made.resume()
    assert failure(record)[0] is None and seen(program, record, 1) == 3


def test_a_flow_started_by_a_firing_shares_after_the_next_rounds_stages():
    """A firing starts a second pipe. Main reads 2 L/h until the next share, then 1 L/h."""
    b = deliveries(after(q(1, 'h')), after(q(0, 'h'), assign(this.seen, named('tank').main.actual_rate)))
    fired = when(t >= q(1, 'h'), start(this.deliver), reset=reset_when(False))
    b.setup(start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert record.failure is None and seen(program, record, 1) == 2
    b = deliveries(
        after(q(1, 'h')), after(q(0, 'h'), assign(this.seen, named('tank').main.actual_rate)), fired=fired
    )
    b.setup(start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert record.failure is None
    assert seen(program, record, 1) == 2
    b = deliveries(
        after(q(1, 'h')),
        after(q(0, 'h')),
        after(q(0, 'h'), assign(this.seen, named('tank').main.actual_rate)),
        fired=fired,
    )
    b.setup(start(named('ops').look))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert failure(record)[0] is None and seen(program, record, 1) == 1
