"""The order of the claims (`network.claim_order`): an endpoint's rule ranks every claim of its flows,
named by a solver or not, and a solver's own sharing acts only among the claims that those rules
leave equal (the owner's rule after G2, docs/design/decisions.md, change 19; re-audit row 07).

Two rules, on small random networks with priorities (stocked, empty, full stores and `[0, 0]`
junctions, endpoints with capacities, requests and `priority(...)`, and with reversible routes and
flows with legs in half of them). Each network has a closed tap into each store (capacity zero, no
request), which a provider's solver names, so that every flow is in the solver's calculation; the
solver names nothing else (the reference: local sharing inside the solver, with the same release of
a store that an answer moves off its bound) or a random subset of the flows as well, with no
objective and no relation. Neither compares with the oracle: each compares the engine with itself.

1. A requesting flow that the solver does not name is served as when the solver names nothing
   (spec, "Selection order": "Flows that no solver determines follow their own endpoints").
2. Where an endpoint ranks a pipe ahead of another, closing the other (its capacity zero) raises the
   first's rate with the flows named only where it does with none named: naming flows never lets a
   lower-ranked flow, or what it carries onward, take from a flow ranked ahead of it.

Then the audit's case and its variants, worked by hand: a hospital-first outlet of 1 L/h with a
solver that names the garden alone serves the hospital first (it gave 0 and 1 L/h), shares 1/2 and
1/2 when the outlet is proportional, and the spec's junctions with a solver of B and C alone keep
1/2, 1/4 and 1/4, and with all four named and A ahead of the onward pipe keep A's 1 L/h.
"""

from __future__ import annotations

import random

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    endpoint,
    flow,
    given,
    legs,
    local,
    named,
    priority,
    proportional,
    q,
    route,
    solve_for,
    solver,
    this,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
TIMES = (0, 0.5, 1, 2, 3)
STORES = {'stocked': (10, 0, 100), 'empty': (0, 0, 100), 'full': (10, 0, 10), 'junction': (0, 0, 0)}
TOLERANCE = (
    1e-6  # the solve library's precision (`solve/solver.py` CHECK) against local sharing's exact rates
)


def drawn(seed, routes=False):
    """The draws of a random network (as `test_local_sharing.network`): (its random generator, the
    kind of each store, the pipes, the routes and the flows with legs, each pipe and leg as (source,
    sink, request, capacity) with store numbers or None)."""
    rng = random.Random(seed)
    count = rng.randint(2, 4)
    kinds = [rng.choice(list(STORES)) for _ in range(count)]
    ends = list(range(count))

    def directed():
        source = rng.choice([None, *ends])
        sink = rng.choice([s for s in [None, *ends] if s != source or s is None])
        if source is None and sink is None:
            sink = rng.choice(ends)
        request = rng.choice([0, 0.5, 1, 2, 3])
        capacity = rng.choice([None, None, 1, 2, 4, 'request'])
        return source, sink, request, request if capacity == 'request' else capacity

    pipes = [directed() for _ in range(rng.randint(2, 6))]
    links, restores = [], []
    if routes:
        for _ in range(rng.randint(1, 2)):
            first, second = rng.sample(ends, 2)
            links.append((first, second, rng.choice([-3, -1, 0, 0.5, 2]), rng.choice([None, 1, 2.5])))
        for _ in range(rng.randint(0, 2)):
            restores.append([directed() for _ in range(2)])
    return rng, kinds, pipes, links, restores


def network(seed, routes=False, named_flows=(), closed=(), ranking=False, extra=None, solved=True):
    """A random program of local sharing (as `test_local_sharing.network`), with the pipes `closed`
    (their numbers) at capacity zero, a closed tap into each store and a provider's solver that names
    the taps and `named_flows`: (program, the keys of the requesting flows by name, the ranked pairs
    of pipes (a, b) that an endpoint ranks a ahead of b, and the names of every flow). With `ranking`,
    nearly every endpoint has a setting, a priority where it has two connections and a capacity, so
    that ranked flows compete. `extra` adds a closed pipe (source, sink, request), store numbers or
    None, as the flow `x.pipe`; `solved` False leaves out the taps and the solver: local sharing."""
    rng, kinds, pipes, links, restores = drawn(seed, routes)
    ends = list(range(len(kinds)))
    incident = {(s, side): [] for s in ends for side in ('outflow', 'inflow')}

    def meets(source, sink, item):
        if source is not None:
            incident[(source, 'outflow')].append(item)
        if sink is not None:
            incident[(sink, 'inflow')].append(item)

    for k, (source, sink, _, _) in enumerate(pipes):
        meets(source, sink, (f'f{k}', named(f'f{k}').pipe))
    for k, (first, second, _, _) in enumerate(links):
        meets(first, second, (None, named(f'r{k}').link.forward))
        meets(second, first, (None, named(f'r{k}').link.backward))
    for k, pair in enumerate(restores):
        for name, (source, sink, _, _) in zip('ab', pair):
            meets(source, sink, (None, getattr(named(f'g{k}').restore, name)))
    b = Builder(UNITS)
    ranked = set()
    for s, kind in enumerate(kinds):
        start, lower, upper = STORES[kind]
        settings = {}
        for side in ('outflow', 'inflow'):
            if rng.random() < (0.9 if ranking else 0.4):
                mine = incident[(s, side)]
                allocation = proportional()
                if len(mine) >= 2 and rng.random() < (0.9 if ranking else 0.6):
                    listed = rng.sample(mine, rng.randint(1, len(mine)))
                    allocation = priority(*(path for _, path in listed))
                    rest = [item for item in mine if all(item is not other for other in listed)]
                    classes = [[item] for item in listed] + [rest]
                    for i, ahead in enumerate(classes):
                        for behind in classes[i + 1 :]:
                            ranked.update(
                                (a, c) for a, _ in ahead for c, _ in behind if a is not None and c is not None
                            )
                settings[side] = endpoint(
                    capacity=rng.choice(
                        [q(1.5, 'L/h'), q(3, 'L/h')] if ranking else [None, q(1.5, 'L/h'), q(3, 'L/h')]
                    ),
                    request=rng.choice([None, None, q(2, 'L/h'), q(5, 'L/h')]),
                    allocation=allocation,
                )
        b.entity(f's{s}', value('water', 'L', start, lower=lower, upper=upper, **settings))

    def end(s, outside):
        return outside if s is None else named(f's{s}').water

    def rate(number):
        return None if number is None else q(number, 'L/h')

    keys, everything = {}, []
    for k, (source, sink, request, cap) in enumerate(pipes):
        capacity = 0 if k in closed else cap
        b.entity(
            f'f{k}',
            flow(
                'pipe', end(source, SOURCE), end(sink, SINK), request=rate(request), capacity=rate(capacity)
            ),
        )
        everything.append((f'f{k}', named(f'f{k}').pipe, 'actual_rate'))
        if request:
            keys[f'f{k}'] = Key(f'f{k}', ('pipe', 'actual_rate'))
    for k, (first, second, request, capacity) in enumerate(links):
        b.entity(
            f'r{k}',
            route(
                'link', end(first, None), end(second, None), request=rate(request), capacity=rate(capacity)
            ),
        )
        everything.append((f'r{k}', named(f'r{k}').link, 'actual_rate'))
        if request:
            keys[f'r{k}'] = Key(f'r{k}', ('link', 'actual_rate'))
    for k, pair in enumerate(restores):
        parts = [
            flow(name, end(source, SOURCE), end(sink, SINK), request=rate(request), capacity=rate(capacity))
            for name, (source, sink, request, capacity) in zip('ab', pair)
        ]
        b.entity(f'g{k}', legs('restore', *parts))
        everything.append((f'g{k}', named(f'g{k}').restore, 'served_fraction'))
        if any(request for _, _, request, _ in pair):
            keys[f'g{k}'] = Key(f'g{k}', ('restore', 'served_fraction'))
    if extra is not None:
        source, sink, request = extra
        b.entity(
            'x',
            flow('pipe', end(source, SOURCE), end(sink, SINK), request=rate(request), capacity=q(0, 'L/h')),
        )
        everything.append(('x', named('x').pipe, 'actual_rate'))
    if not solved:
        return b.finish(), keys, sorted(ranked), [name for name, _, _ in everything]
    b.entity('taps', *(flow(f't{s}', SOURCE, named(f's{s}').water, capacity=q(0, 'L/h')) for s in ends))
    mine = [item for item in everything if item[0] in named_flows]
    mine += [(f't{s}', getattr(named('taps'), f't{s}'), 'actual_rate') for s in ends]
    parts = [given(name, path) for name, path, _ in mine]
    parts += [solve_for(getattr(getattr(local, name), field)) for name, _, field in mine]
    b.entity('provider', solver('plan', *parts))
    return b.finish(), keys, sorted(ranked), [name for name, _, _ in everything]


def chosen(seed, names):
    """A random nonempty subset of the flows for the solver to name, drawn apart from the network."""
    rng = random.Random(10_000 + seed)
    return set(rng.sample(names, rng.randint(1, len(names))))


def rates(program, keys, horizon=TIMES[-1]):
    """{name: the values at TIMES} of `keys`, or None where the run fails."""
    record = run(program, Configuration(Request(horizon)))
    if record.failure is not None:
        return None
    return {name: read(record, program, [key], list(TIMES))[0].values for name, key in keys.items()}


def close(found, expected):
    return all(a == pytest.approx(b, rel=TOLERANCE, abs=TOLERANCE) for a, b in zip(found, expected))


def unnamed_keep_local_sharing(seed, routes):
    program, keys, _, names = network(seed, routes)
    alone = rates(program, keys)
    if alone is None:
        return  # no answer here (a ring, a request at a route's endpoint)
    mine = chosen(seed, names)
    solved = rates(network(seed, routes, mine)[0], keys)
    assert solved is not None, (seed, sorted(mine))
    for name in keys:
        if name not in mine:
            assert close(solved[name], alone[name]), (seed, sorted(mine), name, solved[name], alone[name])


@pytest.mark.parametrize('seed', range(60))
@pytest.mark.parametrize('routes', [False, True], ids=['pipes', 'routes'])
def test_a_flow_that_the_solver_does_not_name_keeps_its_local_sharing(seed, routes):
    unnamed_keep_local_sharing(seed, routes)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(60, 1060))
@pytest.mark.parametrize('routes', [False, True], ids=['pipes', 'routes'])
def test_more_flows_that_the_solver_does_not_name_keep_their_local_sharing(seed, routes):
    unnamed_keep_local_sharing(seed, routes)


def priorities_hold(seed, routes):
    program, keys, ranked, names = network(seed, routes, ranking=True)
    pairs = [(a, c) for a, c in ranked if a in keys]
    alone = rates(program, keys)
    if alone is None or not pairs:
        return
    mine = chosen(seed, names)
    solved = rates(network(seed, routes, mine, ranking=True)[0], keys)
    assert solved is not None, (seed, sorted(mine))
    for a, c in pairs:
        k = int(c[1:])
        shut = rates(network(seed, routes, closed={k}, ranking=True)[0], keys)
        if shut is None or any(x > y + TOLERANCE for x, y in zip(shut[a], alone[a])):
            continue  # local sharing itself lets the lower-ranked pipe take from the other here (a
            # depth that orders them against the rank, or a store that the closing releases)
        shut = rates(network(seed, routes, mine, closed={k}, ranking=True)[0], keys)
        assert shut is not None, (seed, sorted(mine), c)
        for x, y in zip(shut[a], solved[a]):
            assert x <= y + TOLERANCE * (1 + abs(y)), (seed, sorted(mine), a, c, shut[a], solved[a])


@pytest.mark.parametrize('seed', range(40))
@pytest.mark.parametrize('routes', [False, True], ids=['pipes', 'routes'])
def test_naming_flows_never_lets_a_lower_ranked_one_take_from_a_flow_ranked_ahead(seed, routes):
    priorities_hold(seed, routes)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(40, 640))
@pytest.mark.parametrize('routes', [False, True], ids=['pipes', 'routes'])
def test_naming_flows_never_lets_lower_ranked_ones_take_from_more_flows_ranked_ahead(seed, routes):
    priorities_hold(seed, routes)


# ---- the audit's case and its variants, worked by hand ----------------------------------------------


def outlet(names, policy):
    """A [0, 0] outlet fed 1 L/h, with the hospital's and the garden's deliveries of 1 L/h each, its
    outflow `policy` ('priority': the hospital first; 'proportional') and a solver of `names`."""
    b = Builder(UNITS)
    allocation = (
        priority(named('hospital').delivery, named('garden').delivery)
        if policy == 'priority'
        else proportional()
    )
    out = b.entity(
        'outlet',
        value('water', 'L', 0, lower=0, upper=0, outflow=endpoint(allocation=allocation)),
        flow('feed', SOURCE, this.water, capacity=q(1, 'L/h')),
    )
    for name in ('hospital', 'garden'):
        b.entity(name, flow('delivery', out.water, SINK, request=q(1, 'L/h')))
    parts = [given(name, named(name).delivery) for name in names]
    parts += [solve_for(getattr(local, name).actual_rate) for name in names]
    b.entity('provider', solver('plan', *parts))
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert record.failure is None, record.failure
    keys = [Key(name, ('delivery', 'actual_rate')) for name in ('hospital', 'garden')]
    return tuple(reading.values for reading in read(record, program, keys, [0, 0.5]))


@pytest.mark.parametrize(
    'names, policy, expected',
    [
        (('garden',), 'priority', (1, 0)),
        (('hospital',), 'priority', (1, 0)),
        (('hospital', 'garden'), 'priority', (1, 0)),
        (('garden',), 'proportional', (0.5, 0.5)),
        (('hospital',), 'proportional', (0.5, 0.5)),
        (('hospital', 'garden'), 'proportional', (0.5, 0.5)),
    ],
)
def test_an_outlets_rule_ranks_its_flows_whichever_a_solver_names(names, policy, expected):
    """Re-audit row 07: the outlet passes the 1 L/h that its feed brings. Priority gives the hospital
    first access, 1 L/h, and the garden the remainder, none; proportional sharing serves each half of
    its request. The hospital and the garden share the outlet's endpoint, so its rule ranks them
    whichever of them the solver names (a solver of the garden alone gave 0 and 1 L/h)."""
    hospital, garden = outlet(names, policy)
    assert hospital == pytest.approx((expected[0],) * 2, abs=1e-9)
    assert garden == pytest.approx((expected[1],) * 2, abs=1e-9)


def junctions(names, first_policy=None):
    """The spec's junctions ("Sharing is local by default") with a solver of `names` (of to_a,
    onward, to_b, to_c) and the first junction's outflow `first_policy` (None: proportional; 'a':
    A ahead of the onward pipe): the rates of A, onward, B and C at 0 and 0.5 h."""
    b = Builder(UNITS)
    second = b.entity(
        'second',
        value('water', 'L', 0, lower=0, upper=0),
        flow('to_b', this.water, SINK, request=q(1, 'L/h')),
        flow('to_c', this.water, SINK, request=q(1, 'L/h')),
    )
    settings = {}
    if first_policy == 'a':
        settings['outflow'] = endpoint(allocation=priority(named('first').to_a))
    first = b.entity(
        'first',
        value('water', 'L', 0, lower=0, upper=0, **settings),
        flow('feed', SOURCE, this.water, capacity=q(1, 'L/h')),
        flow('to_a', this.water, SINK, request=q(1, 'L/h')),
        flow('onward', this.water, second.water, request=q(1, 'L/h')),
    )
    paths = {'to_a': first.to_a, 'onward': first.onward, 'to_b': second.to_b, 'to_c': second.to_c}
    parts = [given(name, paths[name]) for name in names]
    parts += [solve_for(getattr(local, name).actual_rate) for name in names]
    b.entity('provider', solver('plan', *parts))
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert record.failure is None, record.failure
    keys = [Key('first', ('to_a', 'actual_rate')), Key('first', ('onward', 'actual_rate'))]
    keys += [Key('second', ('to_b', 'actual_rate')), Key('second', ('to_c', 'actual_rate'))]
    return [reading.values for reading in read(record, program, keys, [0, 0.5])]


@pytest.mark.parametrize(
    'names, first_policy, expected',
    [
        (('to_b', 'to_c'), None, (0.5, 0.5, 0.25, 0.25)),
        (('to_a', 'to_b', 'to_c'), None, (0.5, 0.5, 0.25, 0.25)),
        (('to_a', 'onward', 'to_b', 'to_c'), None, (1 / 3, 2 / 3, 1 / 3, 1 / 3)),
        (('to_b', 'to_c'), 'a', (1, 0, 0, 0)),
        (('to_a', 'onward', 'to_b', 'to_c'), 'a', (1, 0, 0, 0)),
    ],
    ids=['b-and-c', 'a-b-and-c', 'all-four', 'b-and-c-a-first', 'all-four-a-first'],
)
def test_the_junctions_keep_the_first_junctions_rule_whatever_the_solver_names(names, first_policy, expected):
    """Worked by hand from the spec's junctions: 1 L/h reaches the first junction. Its outflow shares
    between A and the onward pipe by its rule, which ranks them whether the solver names them or not:
    with the onward pipe not named it splits 1/2 and 1/2, and the second junction splits its 1/2
    between B and C, 1/4 each, whatever the solver names downstream (a solver of B and C once took
    the whole 1 L/h for them and left A none). With the four rates named and no priority, the solver
    shares across its endpoints: 1/3 each, the onward pipe carrying 2/3 (spec). With A ahead of the
    onward pipe, A takes the 1 L/h first, and B and C, which the onward pipe serves, wait for what it
    leaves: none."""
    found = junctions(names, first_policy)
    for values, rate in zip(found, expected):
        assert values == pytest.approx((rate, rate), abs=1e-9)
