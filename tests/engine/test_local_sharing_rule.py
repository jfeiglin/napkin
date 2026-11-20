"""Local sharing at the moments of a run, against the oracle (spec, "Local allocation", the routes,
the junctions and "Flows created during a run").

The rules, each from the spec:

- **The rates of an instant are those that hold after it.** "At that instant the rate becomes zero"
  (the tank of "Flows and algebraic solvers"), and the engine "follows the rate through the interval"
  (spec, "A rate can follow a moving quantity"). So a store on a bound is held there while its sharing
  keeps it there: where the rates found with it held move it off its bound, it is free just after, and
  its rates are those of local sharing with it free (where those would move it back past its bound,
  it stays held, as a declared solver's store does). So a run does not depend on where its moments
  fall: a stage that changes nothing that the network reads changes no rate.
- **A junction passes what it takes in.** At `[0, 0]` "total inflow equals total outflow", whatever
  meets it: a route, a flow with legs into a full store, a directed flow.
- **No answer is a failure where the flows settle.** A ring of stores that pass supply or room around
  has no answer of local sharing; whether there is one depends on the levels of the stores and on the
  connections that can carry flow, which a setup and a stage can change. So the run stops by name
  where the flows settle with the ring there: after the setup, or at the moment it forms. So too where
  no rates hold just after a moment: held at its bound, a store's sharing moves it off, and free, back
  past it (PLAN, change 10: a run that cannot answer stops by name, never with a quietly different
  answer).
- **Every endpoint exists for the whole run.** "A stored quantity gains an `outflow` scope when it
  supplies a flow and an `inflow` scope when it receives one", with a request that "defaults to zero"
  and proportional sharing: a stage may give one that the model never configured an allocation or a
  request.

The rule test: small random networks of stores of every kind (stocked, empty, full, small and `[0, 0]`
junctions), with directed flows, routes between any two of them, flows with legs into full stores,
endpoints with capacities, requests and priorities or none at all, and an operator whose stages set
requests, capacities and allocations (at configured endpoints and at ones that nothing configured),
start an occurrence whose flow joins and later leaves, and write an unrelated value at times between
(a moment that changes nothing that the network reads); the setup now and then sets a store. Rates are
read only after a wait. The oracle (`tests/reference/`) runs the same program in exact fractions: both
runs fail at the same time and for the same reason, or both pass with the same values; straight, and
with a stop before the reading stage and an edit of a store, resumed in place and from the saved state.
The named cases below state each rule with numbers worked by hand.
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
    ifelse,
    legs,
    local,
    named,
    priority,
    proportional,
    q,
    route,
    start,
    t,
    this,
    value,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.errors import NotCovered, RunFailed
from tests.reference.from_program import config_of, model_of, scale_at, value_at
from tests.reference.run import Run as Oracle

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
HORIZON = 4
TIMES = [Fraction(k, 4) for k in range(4 * HORIZON + 1)]
STORES = {  # start, lower, upper
    'stocked': (6, 0, 100),
    'empty': (0, 0, 100),
    'full': (10, 0, 10),
    'junction': (0, 0, 0),
    'small': (2, 0, 8),
}
LOOK = 'ops.look.step[0]'  # the reading stage, where the runs with an edit stop
# Where local sharing has no answer, the oracle has none (`NotCovered`) and the engine stops, naming
# the stores or the endpoint: a ring, a request where a route meets, and a store that no rates hold
# just after a moment (held, they move it off its bound; free, back past it).
NO_ANSWER = (
    'ring of stores',
    'a request at an endpoint that the route',
    'switch back and forth at its bound',
)
STALE = 'is read before'


def rate(number):
    return None if number is None else q(number, 'L/h')


def network(seed):
    """A random program (see the module): stores `s<k>.water`, flows `f<k>.pipe`, routes `r<k>.link`,
    a flow with legs `g0.restore`, and the operator `ops`. Gives the program, the keys to compare, and
    an edit of a store (its key and a level within its bounds)."""
    rng = random.Random(seed)
    count = rng.randint(2, 4)
    kinds = [rng.choice(list(STORES)) for _ in range(count)]
    ends = list(range(count))
    full = [s for s in ends if kinds[s] == 'full'] or ends

    def directed(into=None):
        source = rng.choice([None, *ends])
        sink = into if into is not None else rng.choice([None, *ends])
        if sink == source:
            sink = None
        if source is None and sink is None:
            sink = rng.choice(ends)
        return source, sink, rng.choice([0, Fraction(1, 2), 1, 2, 4]), rng.choice([None, None, 1, 2, 4])

    flows = [directed() for _ in range(rng.randint(1, 4))]
    links = []
    for _ in range(rng.choice([0, 1, 1, 2])):  # a route between any two stores, of any kind
        first, second = rng.sample(ends, 2)
        links.append((first, second, rng.choice([-2, -1, 0, 1, 2]), rng.choice([None, 1, 4])))
    restores = []
    if rng.random() < 0.4:  # a flow with legs, a leg into a full store more often than not
        into = rng.choice(full) if rng.random() < 0.7 else None
        restores.append([directed(into), directed()])
    incident = {(s, side): [] for s in ends for side in ('outflow', 'inflow')}
    routed = set()  # the endpoints that a route meets: a request there has no answer

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
        routed |= {(first, 'outflow'), (first, 'inflow'), (second, 'outflow'), (second, 'inflow')}
    for k, pair in enumerate(restores):
        for name, (source, sink, _, _) in zip('ab', pair):
            meets(source, sink, getattr(named(f'g{k}').restore, name))
    delivered = rng.choice(ends)  # the store that the tap of an occurrence of `deliver` drains
    b = Builder(UNITS)
    for s, kind in enumerate(kinds):
        level, lower, upper = STORES[kind]
        settings = {}
        for side in ('outflow', 'inflow'):
            # Some endpoints are configured; the others exist all the same, and a stage may set them.
            if rng.random() < 0.35:
                mine = incident[(s, side)]
                allocation = proportional()
                if len(mine) >= 2 and rng.random() < 0.6:
                    allocation = priority(*rng.sample(mine, rng.randint(1, len(mine))))
                request = None if (s, side) in routed else rng.choice([None, None, q(1, 'L/h'), q(3, 'L/h')])
                capacity = rng.choice([None, q(1, 'L/h'), q(3, 'L/h')])
                settings[side] = endpoint(capacity=capacity, request=request, allocation=allocation)
        b.entity(f's{s}', value('water', 'L', level, lower=lower, upper=upper, **settings))

    def end(s, outside):
        return outside if s is None else named(f's{s}').water

    for k, (source, sink, request, capacity) in enumerate(flows):
        unit = 'L/h' if source is None and sink is None else ''
        made = flow(
            'pipe',
            end(source, SOURCE),
            end(sink, SINK),
            request=rate(request),
            capacity=rate(capacity),
            unit=unit,
        )
        b.entity(f'f{k}', made)
    for k, (first, second, request, capacity) in enumerate(links):
        made = route(
            'link', end(first, None), end(second, None), request=rate(request), capacity=rate(capacity)
        )
        b.entity(f'r{k}', made)
    for k, pair in enumerate(restores):
        parts = [
            flow(name, end(source, SOURCE), end(sink, SINK), request=rate(request), capacity=rate(capacity))
            for name, (source, sink, request, capacity) in zip('ab', pair)
        ]
        b.entity(f'g{k}', legs('restore', *parts))

    # What a stage changes: requests, capacities, allocations (also at endpoints that nothing
    # configured), and now and then a store, or a start of `deliver`.
    changes = []
    for k, (_, _, _, capacity) in enumerate(flows):
        changes.append(assign(named(f'f{k}').pipe.request, rate(rng.choice([0, 1, 3]))))
        if capacity is not None:
            changes.append(assign(named(f'f{k}').pipe.capacity, rate(rng.choice([0, Fraction(1, 2), 2]))))
    for k in range(len(links)):
        changes.append(assign(named(f'r{k}').link.request, rate(rng.choice([-2, -1, 1, 2]))))
    for k in range(len(restores)):
        changes.append(assign(named(f'g{k}').restore.b.request, rate(rng.choice([0, 1, 3]))))
    for s in ends:
        for side in ('outflow', 'inflow'):
            mine = incident[(s, side)]
            if mine:
                chosen = (
                    priority(*rng.sample(mine, rng.randint(1, len(mine))))
                    if rng.random() < 0.7
                    else proportional()
                )
                changes.append(assign(getattr(named(f's{s}').water, side).allocation, chosen))
        if (s, 'outflow') not in routed and incident[(s, 'outflow')] and rng.random() < 0.3:
            changes.append(assign(named(f's{s}').water.outflow.request, rate(rng.choice([1, 2]))))
    if rng.random() < 0.3:
        s = rng.choice(ends)
        _, lower, upper = STORES[kinds[s]]
        changes.append(assign(named(f's{s}').water, q(rng.choice([lower, upper]), 'L')))
    changes.append(start(this.deliver))

    # What a stage reads after a wait: rates of flows, of a route and of the endpoints.
    reads = [named(f'f{k}').pipe.actual_rate for k in range(len(flows))]
    reads += [named(f'r{k}').link.actual_rate for k in range(len(links))]
    reads += [named(f'g{k}').restore.served_fraction for k in range(len(restores))]
    first = rng.choice([1, 2])
    second = rng.choice([Fraction(1, 2), 1])
    tap = flow('tap', named(f's{delivered}').water, SINK, request=rate(rng.choice([1, 2])))
    picked = rng.sample(reads, min(2, len(reads)))
    looked = [assign(getattr(this, f'seen{k}'), path) for k, path in enumerate(picked)]
    b.entity(
        'ops',
        value('mark', '', 0),
        value('seen0', '', -1),
        value('seen1', '', -1),
        event(
            'change',
            after(q(first, 'h'), *rng.sample(changes, rng.randint(1, 2))),
            after(q(second, 'h'), *rng.sample(changes, rng.randint(1, 2))),
        ),
        # A moment that changes nothing that the network reads, at a time between the changes.
        event(
            'quiet',
            after(q(rng.choice([Fraction(1, 2), Fraction(3, 2), Fraction(5, 2)]), 'h'), assign(this.mark, 1)),
        ),
        event('look', after(q(Fraction(15, 4), 'h'), *looked)),
        event('deliver', tap, after(q(rng.choice([1, 2]), 'h'))),
    )
    setup = [start(named('ops').change), start(named('ops').look)]
    if rng.random() < 0.5:
        setup.append(start(named('ops').quiet))
    if rng.random() < 0.2:
        setup.append(start(named('ops').deliver))
    if rng.random() < 0.3:  # the setup sets a store, which can make or break a ring
        s = rng.choice(ends)
        _, lower, upper = STORES[kinds[s]]
        setup.append(
            assign(named(f's{s}').water, q(rng.choice([lower, Fraction(lower + upper, 2), upper]), 'L'))
        )
    rng.shuffle(setup)
    b.setup(*setup)
    keys = [Key(f's{s}', ('water',)) for s in ends] + [Key('ops', (f'seen{k}',)) for k in range(len(picked))]
    edited = rng.choice(ends)
    _, lower, upper = STORES[kinds[edited]]
    return b.finish(), keys, (Key(f's{edited}', ('water',)), rng.choice([lower, upper]))


def oracle_of(program, configuration, stops):
    """The oracle's run of a program: (the run, its failure or None, and the time of a `NotCovered`
    or None), with each stop of `stops` made as in `from_program.run_of`."""
    made = Oracle(model_of(program), config_of(program, configuration))
    made.breakpoints = [(origin, None) for origin, _ in stops]
    try:
        made.run()
        for origin, edits in stops:
            if made.paused is None:
                raise RunFailed(f'the run never stops at {origin}')
            made.breakpoints.remove((origin, None))
            for key, number in edits:
                made.edit(key.owner, key.steps[0], Fraction(number) * scale_at(program, key))
            made.resume()
    except NotCovered as problem:
        return made, problem, made.view.t
    except RunFailed as problem:
        return made, problem, None
    return made, None, None


def engine_records(program, configuration, edit):
    """The engine's records: straight through, or with `edit` made at a stop before the reading stage,
    resumed in place and from the checkpoint's saved state (what a fresh process loads)."""
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
    oracle, failed, uncovered = oracle_of(program, configuration, [(LOOK, [change])] if edit else [])
    if uncovered is None and isinstance(failed, NotCovered):
        return
    for record in engine_records(program, configuration, change if edit else None):
        message = None if record.failure is None else record.failure.detail('message')
        if uncovered is not None:
            # No answer: the engine stops at the same time, naming the stores or the endpoint; what
            # the oracle cannot settle for want of a method (anything else) is not compared.
            if not any(reason in str(failed) for reason in (*NO_ANSWER[::2], 'reversible flow at that')):
                return
            assert message is not None, (seed, str(failed))
            assert any(reason in message for reason in NO_ANSWER), (seed, message)
            assert record.failure.t == pytest.approx(float(uncovered)), (seed, str(failed), message)
            horizon = uncovered
        elif failed is not None:
            assert message is not None, (seed, str(failed))
            assert record.failure.t == pytest.approx(float(oracle.view.t)), (seed, str(failed), message)
            assert (STALE in message) == (STALE in str(failed)), (seed, str(failed), message)
            horizon = oracle.view.t
        else:
            assert message is None, (seed, message)
            horizon = Fraction(HORIZON + 1)
        times = [time for time in TIMES if time < horizon]
        for key in keys:
            found = read(record, program, [key], [float(time) for time in times])[0].values
            for time, number in zip(times, found):
                expected = float(value_at(oracle, program, key, time))
                assert number == pytest.approx(expected, rel=1e-9, abs=1e-9), (seed, str(key), float(time))


@pytest.mark.parametrize('seed', range(150))
def test_local_sharing_at_every_moment_is_the_oracles(seed):
    compare(seed)


@pytest.mark.parametrize('seed', range(150))
def test_an_edit_at_a_stop_before_a_read_shares_as_the_oracle_does(seed):
    compare(seed, edit=True)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(150, 1650))
def test_more_networks_share_at_every_moment_as_the_oracle_does(seed):
    compare(seed)
    compare(seed, edit=True)


# ---- the named cases, worked by hand -----------------------------------------------------------------


def both(program, key, times, horizon=HORIZON, stops=()):
    """The values at a key at `times` of the engine's run and of the oracle's, and their failures."""
    configuration = Configuration(Request(horizon))
    record = run(program, configuration)
    oracle, failed, _ = oracle_of(program, configuration, stops)
    engine = (
        None if record.failure else list(read(record, program, [key], [float(x) for x in times])[0].values)
    )
    exact = None if failed else [float(value_at(oracle, program, key, Fraction(x))) for x in times]
    return engine, exact, record.failure and record.failure.detail('message'), failed


def route_against_its_request(stage=None):
    """`s0` full at 10 L of [0, 10], fed 1/2 L/h from outside; a route s0 <-> s1 that asks 2 L/h from
    s1 to s0, of capacity 1 L/h; `s1` empty, of [0, 100]; and a stage at 2 h, or none."""
    b = Builder(UNITS)
    feed = flow('feed', SOURCE, this.water, request=q(Fraction(1, 2), 'L/h'), capacity=q(4, 'L/h'))
    b.entity('s0', value('water', 'L', 10, lower=0, upper=10), feed)
    b.entity('s1', value('water', 'L', 0, lower=0, upper=100))
    link = route('link', named('s0').water, named('s1').water, request=q(-2, 'L/h'), capacity=q(1, 'L/h'))
    b.entity('r0', link)
    b.entity('ops', value('mark', '', 0), *([event('look', after(q(2, 'h'), stage))] if stage else []))
    if stage:
        b.setup(start(named('ops').look))
    return b.finish()


@pytest.mark.parametrize(
    'stage', [None, assign(named('ops').mark, 1), assign(named('r0').link.capacity, q(1, 'L/h'))]
)
def test_a_route_against_its_request_out_of_a_full_store_carries_what_holds_just_after(stage):
    """The route's claim, 2 L/h from s1 to s0, is served at no state: s0 is full, and the only room
    in it is what the route itself takes out. A fulfilled fraction counts from zero (spec, "Selection
    order": "A positive request measures its fulfilled fraction up to 100%"; the backward leg
    "exposes the positive part of its negation"), so going forward the route's fraction is zero, not
    below, and it may carry against its request to make room for the feed ("An edge may carry more
    than its own request to meet another request"): the feed is served in full, 1/2 L/h, from the
    start, and s1 fills at 1/2 L/h, whatever stage falls at 2 h: 1/2 L at 1 h, 1.25 L at 2.5 h, 2 L
    at 4 h. (Before, the route's fraction was its signed rate over its request, below zero going
    forward: the oracle stopped both at its next moment, the engine at its own.)"""
    program = route_against_its_request(stage)
    engine, exact, failure, failed = both(program, Key('s1', ('water',)), [1, Fraction(5, 2), 4])
    assert failure is None and failed is None
    assert engine == pytest.approx([0.5, 1.25, 2.0], rel=1e-12) and exact == [0.5, 1.25, 2.0]
    engine, exact, _, _ = both(program, Key('r0', ('link', 'actual_rate')), [0, 1, 3])
    assert engine == pytest.approx([0.5, 0.5, 0.5], rel=1e-12) and exact == [0.5, 0.5, 0.5]


def fed(test):
    """A store from 0 L, unbounded above, fed from outside at 1 L/h while `test` holds, else 3 L/h."""
    b = Builder(UNITS)
    request = formula(ifelse(test, q(1, 'L/h'), q(3, 'L/h')))
    b.entity('s0', value('water', 'L', 0, lower=0), flow('feed', SOURCE, this.water, request=request))
    return b.finish()


@pytest.mark.parametrize(
    'test, expected',
    [
        (t <= q(2, 'h'), [1, 2, 5, 8]),  # closed at 2 h, false just after: 3 L/h from 2 h
        (t >= q(2, 'h'), [3, 6, 7, 8]),  # true at 2 h and after: 1 L/h from 2 h
        (this.water <= q(2, 'L'), [1, 2, 5, 8]),  # the store crosses 2 L at 2 h, rising
    ],
)
def test_the_rate_after_a_moment_is_that_of_the_state_just_after_it(test, expected):
    """A comparison at the closed side of its switch at a moment holds there, and not just after: the
    rate over the interval after the moment is the one of the state just after it. So the store gains
    1 L/h to 2 L at 2 h, then 3 L/h: 5 L at 3 h and 8 L at 4 h (the oracle carried the 1 L/h of the
    instant on, 3 L and 4 L)."""
    engine, exact, failure, failed = both(fed(test), Key('s0', ('water',)), [1, 2, 3, 4])
    assert failure is None and failed is None
    assert engine == pytest.approx(expected, rel=1e-9) and exact == expected


def test_a_junction_between_a_route_and_legs_into_a_full_store_passes_what_it_takes_in():
    """`j` at [0, 0] meets one route, to the full store `f`: what flows in is what flows out, so the
    route carries exactly zero. The legs draw from the empty store `e`, which nothing feeds: their
    fraction is zero. `f` passes the room of its outflow `out` (4 L/h at most) to the feeds `p1` and
    `p2`, in one tier with it: `out` serves its 2 L/h in full at 4 L/h, and p1 / 2 = p2 / 3 = 4/5, so
    8/5 and 12/5 L/h. (Before, the rounding of the engine's selection left the route at -1.4e-17 L/h,
    and the run stopped: "local sharing moves it past its bound at 0 h".)"""
    b = Builder(UNITS)
    b.entity('j', value('water', 'L', 0, lower=0, upper=0))
    b.entity('f', value('water', 'L', 10, lower=0, upper=10))
    b.entity('e', value('water', 'L', 0, lower=0, upper=100))
    b.entity(
        'r0', route('link', named('j').water, named('f').water, request=q(-2, 'L/h'), capacity=q(3, 'L/h'))
    )
    first = flow('a', named('e').water, named('f').water, request=q(Fraction(1, 3), 'L/h'))
    second = flow('b', named('f').water, SINK, request=q(1, 'L/h'), capacity=q(2, 'L/h'))
    b.entity('g0', legs('restore', first, second))
    b.entity('out', flow('pipe', named('f').water, SINK, request=q(2, 'L/h'), capacity=q(4, 'L/h')))
    b.entity('p1', flow('pipe', SOURCE, named('f').water, request=q(2, 'L/h')))
    b.entity('p2', flow('pipe', SOURCE, named('f').water, request=q(3, 'L/h'), capacity=q(4, 'L/h')))
    program = b.finish()
    for key, expected in (
        (Key('r0', ('link', 'actual_rate')), 0),
        (Key('g0', ('restore', 'served_fraction')), 0),
        (Key('out', ('pipe', 'actual_rate')), 4),
        (Key('p1', ('pipe', 'actual_rate')), Fraction(8, 5)),
        (Key('p2', ('pipe', 'actual_rate')), Fraction(12, 5)),
        (Key('j', ('water',)), 0),
        (Key('f', ('water',)), 10),
    ):
        engine, exact, failure, failed = both(program, key, [0, 1, 3], horizon=3)
        assert failure is None and failed is None
        assert engine == pytest.approx([float(expected)] * 3, rel=1e-12, abs=1e-15)
        assert exact == [float(expected)] * 3


def ring(setup=()):
    """Two stores empty at 0 L of [0, 10] that feed each other at 1 L/h, the second also out at
    1/4 L/h: a ring of stores at their lower bound, which local sharing has no answer for."""
    b = Builder(UNITS)
    b.entity(
        's0',
        value('water', 'L', 0, lower=0, upper=10),
        flow('pipe', this.water, named('s1').water, request=q(1, 'L/h')),
    )
    back = flow('pipe', this.water, named('s0').water, request=q(1, 'L/h'))
    out = flow('out', this.water, SINK, request=q(Fraction(1, 4), 'L/h'))
    b.entity('s1', value('water', 'L', 0, lower=0, upper=10), back, out)
    b.entity('ops', value('mark', '', 0))
    b.setup(assign(named('ops').mark, 1), *setup)
    return b.finish()


def test_a_setup_that_breaks_a_ring_runs_and_one_that_keeps_it_stops_after_it():
    """With s0 at 5 L from the setup there is no ring: s1, at its lower bound, passes on what s0
    sends, and its two outflows ask 5/4 L/h, which the pipe from s0, of no capacity, carries in full
    (a request is soft): s0 loses 5/4 L/h and gains 1 L/h back, 5 - t/4 L. Without, the ring stops
    the run at 0 h, where the flows first settle: after the setup, so that a stop at its first
    statement comes first and the failure on resume (before, the engine stopped before the setup)."""
    program = ring([assign(named('s0').water, q(5, 'L'))])
    engine, exact, failure, failed = both(program, Key('s0', ('water',)), [0, 1, 2, 4])
    assert failure is None and failed is None
    assert engine == pytest.approx([5, 4.75, 4.5, 4], rel=1e-12) and exact == [5, 4.75, 4.5, 4]
    program = ring()
    record = run(program, Configuration(Request(HORIZON)))
    assert record.failure.t == 0 and 'ring of stores' in record.failure.detail('message')
    made = Run(Plan.of(program, Configuration(Request(HORIZON))), (Breakpoint('setup[0]'),))
    assert isinstance(made.run(), Checkpoint)
    record = made.resume()
    assert record.failure.t == 0 and 'ring of stores' in record.failure.detail('message')


def tank(change, occurrence=False):
    """A tank of 10 L of [0, 10] with two pipes out, `a` and `c`, whose endpoint nothing configures,
    a stage at 1 h that makes `change`, and with `occurrence` a delivery of 1 L/h for 2 h from the
    setup."""
    b = Builder(UNITS)
    b.entity('s0', value('water', 'L', 10, lower=0, upper=10))
    requests = (q(1, 'L/h'), q(2, 'L/h')) if occurrence else (None, None)
    b.entity('a', flow('pipe', named('s0').water, SINK, request=requests[0]))
    b.entity('c', flow('pipe', named('s0').water, SINK, request=requests[1]))
    tap = flow('tap', named('s0').water, SINK, request=q(1, 'L/h'))
    b.entity('ops', event('change', after(q(1, 'h'), change)), event('deliver', tap, after(q(2, 'h'))))
    b.setup(start(named('ops').change), *([start(named('ops').deliver)] if occurrence else []))
    return b.finish()


def test_an_endpoint_that_only_a_stage_names_is_in_the_network_from_the_start():
    """A stage gives the outflow of the tank, which the model configures nowhere, an allocation, in a
    run where a delivery's flow joins: with stock in the tank every flow carries its request, 4 L/h to
    6 L at 1 h and 2 L at 2 h, when the delivery leaves; then 3 L/h to empty at 2 h 40 min (before,
    "s0.water.outflow.request has no value yet" at 1 h). And a stage gives it a request of 2 L/h, which
    its two pipes, which ask nothing of their own, carry half each: 8 L at 2 h and 4 L at 4 h (before,
    the request was in no set, and nothing flowed). So too for a store of an occurrence: its own stage
    gives its outflow 2 L/h at 1 h, which its pipe carries: 4 L to 1 h, 2 L at 2 h, empty at 3 h, when
    it finishes (before, the tank held its 4 L, and could not finish)."""
    program = tank(assign(named('s0').water.outflow.allocation, priority(named('c').pipe)), occurrence=True)
    engine, exact, failure, failed = both(program, Key('s0', ('water',)), [1, 2, Fraction(5, 2), 3])
    assert failure is None and failed is None
    assert engine == pytest.approx([6, 2, 0.5, 0], rel=1e-12, abs=1e-12) and exact == [6, 2, 0.5, 0]
    program = tank(assign(named('s0').water.outflow.request, q(2, 'L/h')))
    engine, exact, failure, failed = both(program, Key('s0', ('water',)), [1, 2, 4])
    assert failure is None and failed is None
    assert engine == pytest.approx([10, 8, 4], rel=1e-12) and exact == [10, 8, 4]
    engine, exact, _, _ = both(program, Key('a', ('pipe', 'actual_rate')), [Fraction(1, 2), 2])
    assert engine == exact == [0, 1]
    b = Builder(UNITS)
    stage = after(q(1, 'h'), assign(local.tank.outflow.request, q(2, 'L/h')))
    held = value('tank', 'L', 4, lower=0, upper=10)
    b.entity('ops', event('deliver', held, flow('pipe', local.tank, SINK), stage, after(q(2, 'h'))))
    b.setup(start(named('ops').deliver))
    engine, exact, failure, failed = both(b.finish(), Key('ops.deliver#0', ('tank',)), [1, 2, 3, 4])
    assert failure is None and failed is None
    assert engine == pytest.approx([4, 2, 0, 0], abs=1e-12) and exact == [4, 2, 0, 0]
