"""The cases of the spike: small programs, each with the numbers that the spec or a closed form gives.

`python cases.py` prints each case. `test_spike.py` checks them.
"""

from __future__ import annotations

import math

import numpy as np
from engine import Engine, RunStopped
from expr import T, actual, any_active, count_done, count_occ, n_flows, newest, ref, since, sum_request
from program import SINK, SOURCE, After, Assign, Event, Flow, Move, Start, Store, Template, Trigger, Until

INF = math.inf


# ---- the table of "Flows created during a run" -------------------------------------------------------


def flows_table(capacity=INF):
    """Each `deliver` occurrence owns one flow `pipe`, which asks 2 L/h of the tank while it runs.
    A runs from 1 h to 2 h and B from 3 h to 4 h."""
    deliver = Event(
        'deliver',
        params=(('hours', 0.0, 100.0),),
        flows=(Flow('pipe', 'this.water', SINK, request=2.0),),
        steps=(After(ref('hours')),),
    )
    tank = Template('Tank', stores=(Store('water', 100.0, out_capacity=capacity),), events=(deliver,))
    return Engine([tank])


def flows_table_rows():
    """The four rows of the table of the spec, and the request that stays readable on A."""
    engine = flows_table()
    engine.start_at(1.0, 'Tank', 'deliver', args=(1.0,))
    engine.start_at(3.0, 'Tank', 'deliver', args=(1.0,))
    reads = (
        count_occ('this.deliver'),
        n_flows('this.water'),
        sum_request('this.water'),
        actual('this.water'),
    )
    rows = []
    for at in (0.5, 1.5, 2.5, 3.5):
        engine.run(at)
        rows.append(tuple(float(engine.read(x, 'Tank')) for x in reads))
    engine.run(2.5)
    return rows, engine


def frozen_request():
    """After A finishes and before B starts, `deliver.occurrences.at(t).pipe.request` is A's last
    request; once B starts it is B's."""
    engine = flows_table()
    engine.start_at(1.0, 'Tank', 'deliver', args=(1.0,))
    engine.start_at(3.0, 'Tank', 'deliver', args=(1.0,))
    found = {}
    for at in (2.5, 3.5):
        engine.run(at)
        found[at] = (
            float(engine.read(newest('this.deliver', 'pipe.request'), 'Tank')),
            float(engine.read(newest('this.deliver', 'pipe.actual_rate'), 'Tank')),
            float(engine.read(newest('this.deliver', 'started'), 'Tank')),
            bool(engine.read(any_active('this.deliver'), 'Tank')),
        )
    return found


# ---- members that enter and leave a shared limit -----------------------------------------------------


def shared_limit():
    """With a shared limit of 3 L/h and 2 L/h asked by each occurrence: A alone gets 2; A and B get
    1.5 each; B alone gets 2; then the endpoint is empty (spec, "Unknowns that enter and leave a
    running solve"). A runs from 0 h to 2 h and B from 1 h to 3 h."""
    engine = flows_table(capacity=3.0)
    engine.start_at(0.0, 'Tank', 'deliver', args=(2.0,))
    engine.start_at(1.0, 'Tank', 'deliver', args=(2.0,))
    found = []
    for at in (0.5, 1.5, 2.5, 3.5):
        engine.run(at)
        edges = engine.edges
        alive = np.flatnonzero(edges.alive[: edges.n])
        found.append((at, [float(rate) for rate in edges.rate[alive]], float(engine.read(actual('this.water'), 'Tank'))))
    return found, engine


def fresh_formation(seed=0, starts=300, samples=60, limit=7.3):
    """Many occurrences with random requests join and leave one endpoint with a shared limit. At
    random times, the rates of the flows present must equal, bit for bit, those of an endpoint
    formed fresh from its present members, in a shuffled order. The count of times compared and
    the count that differ."""
    from engine import share
    from exact import ExactSum

    rng = np.random.default_rng(seed)
    deliver = Event(
        'deliver',
        params=(('hours', 0.0, 100.0), ('pace', 0.0, 100.0)),
        flows=(Flow('pipe', 'this.water', SINK, request=ref('pace')),),
        steps=(After(ref('hours')),),
    )
    tank = Template('Tank', stores=(Store('water', 1e9, out_capacity=limit),), events=(deliver,))
    engine = Engine([tank])
    for at in np.sort(rng.uniform(0.0, 50.0, starts)).tolist():
        engine.start_at(at, 'Tank', 'deliver', args=(float(rng.uniform(0.1, 5.0)), float(rng.uniform(0.01, 3.0))))
    compared = differ = 0
    sid = int(engine.sids['Tank']['water'][0])
    for at in np.sort(rng.uniform(0.0, 55.0, samples)).tolist():
        engine.run(at)
        members = engine.outs[sid]
        ids = members.now().copy() if members is not None else np.empty(0, dtype=np.int64)
        if not len(ids):
            continue
        rng.shuffle(ids)
        edges = engine.edges
        requests = edges.request[ids]
        fresh = share(requests, edges.capacity[ids], limit, edges.rank[ids], ExactSum(requests.tolist()))
        compared += 1
        differ += int(not np.array_equal(fresh, edges.rate[ids]))
    return compared, differ


def running_total_drift(seed=0, steps=10_000, alive=50):
    """The alternative to the exact sum: a running float total (`+= x` at a join, `-= x` at a
    leave). The count of times, among `steps` joins and leaves, at which it differs from the
    correctly rounded sum of the present members, and the largest difference."""
    rng = np.random.default_rng(seed)
    present, running, differ, worst = [], 0.0, 0, 0.0
    for _ in range(steps):
        if len(present) < alive or rng.random() < 0.5:
            x = float(rng.uniform(0.01, 3.0))
            present.append(x)
            running += x
        else:
            running -= present.pop(int(rng.integers(len(present))))
        exact = math.fsum(present)
        if running != exact:
            differ += 1
            worst = max(worst, abs(running - exact))
    return differ, worst


# ---- a flow that joins must move the time of a crossing ----------------------------------------------


def crossing(forget=False, say=False):
    """A tank at 10 L fills at 1 L/h. An occurrence drains 2 L/h more from 2 h to 4 h. A trigger on
    `>= 16 L` must fire at 10 h. With `forget`, the prediction is not made again: it fires at 6 h,
    when the tank holds 12 L."""
    drain = Event('drain', flows=(Flow('out', 'this.water', SINK, request=2.0),), steps=(After(2.0),))
    alarm = Event(
        'alarm',
        steps=(After(0.0, (Assign('this.level_at_alarm', '=', ref('this.water')), Assign('this.alarm_at', '=', T))),),
        triggers=(Trigger(ref('this.water') >= 16.0, reset=('never',)),),
    )
    tank = Template(
        'Tank',
        fields={'alarm_at': math.nan, 'level_at_alarm': math.nan},
        stores=(Store('water', 10.0),),
        flows=(Flow('fill', SOURCE, 'this.water', request=1.0),),
        events=(drain, alarm),
    )
    engine = Engine([tank], forget_membership=forget, record=True)
    engine.say = say
    engine.start_at(2.0, 'Tank', 'drain')
    engine.run(12.0)
    return engine


def crossing_by_small_steps(step=1e-4):
    """The same tank with no engine: Euler steps of the level, and the first time at 16 L."""
    level, t = 10.0, 0.0
    while level < 16.0:
        rate = 1.0 - (2.0 if 2.0 <= t < 4.0 else 0.0)
        level += rate * step
        t += step
    return t


# ---- triggers and their resets ---------------------------------------------------------------------


def grinder():
    """A grinder with 8 g. Its trigger starts a refill of 50 g at 10 g or below, and a manual start
    asks 50 g at the same time: two refills bring it to 108 g at half an hour."""
    refill = Event(
        'refill',
        params=(('amount', 0.0, 1000.0),),
        locals=(('status', 0.0),),
        steps=(After(0.5, (Assign('this.beans', '+=', ref('amount')), Assign('status', '=', 1.0))),),
        triggers=(Trigger(ref('this.low'), args=(50.0,), reset=('when', ref('this.beans') >= 30.0)),),
    )
    grinder_ = Template(
        'Grinder', fields={'beans': 8.0}, formulas={'low': ref('this.beans') <= 10.0}, events=(refill,)
    )
    engine = Engine([grinder_])
    engine.start_at(0.0, 'Grinder', 'refill', args=(50.0,))
    return engine


def clock():
    """`when t >= 3 h` with `reset after 3 h` fires at 3, 6 and 9 h."""
    inspect = Event(
        'inspect',
        steps=(After(0.0, (Assign('this.inspections', '+=', 1.0),)),),
        triggers=(Trigger(T >= 3.0, reset=('after', 3.0)),),
    )
    return Engine([Template('Plant', fields={'inspections': 0.0}, events=(inspect,))])


def inspect_with_a_delay():
    """`inspect(delay)`: its first stage sets its own copy of `delay` to 2 h, so a call with 3 h has
    its stages at 3 h and at 5 h; then it waits at a gate for a clearance that comes at 7 h."""
    note = Event('note', steps=(After(0.0, (Assign('this.noted_at', '=', T),)),))
    inspect = Event(
        'inspect',
        params=(('delay', 0.0, 100.0),),
        steps=(
            After(ref('delay'), (Assign('this.first_at', '=', T), Assign('delay', '=', 2.0))),
            After(ref('delay'), (Assign('this.second_at', '=', T),), guard=ref('this.safe') >= 1.0),
            Until(ref('this.cleared') >= 1.0),
            After(0.0, (Start('this.note'),)),
        ),
    )
    plant = Template(
        'Plant',
        fields={'safe': 1.0, 'cleared': 0.0, 'first_at': math.nan, 'second_at': math.nan, 'noted_at': math.nan},
        events=(inspect, note),
    )
    engine = Engine([plant])
    engine.start_at(0.0, 'Plant', 'inspect', args=(3.0,))
    engine.write_at(7.0, 'Plant', 'cleared', 1.0)
    return engine


# ---- deliveries from a shared supply (spec, "Delivery experiments on the pinned engine") ------------


def delivery(amount_high=1e9):
    """Each delivery fills its own batch from the shared supply at up to its pace, and moves the
    batch to the tally `delivered` of its lane when it is full."""
    return Event(
        'deliver',
        params=(('amount', 0.0, amount_high), ('pace', 0.0, 1e9)),
        stores=(Store('got', 0.0, upper=ref('amount')),),
        flows=(Flow('pipe', 'this.depot.supply', 'got', request=ref('pace')),),
        steps=(Until(ref('got') >= ref('amount')), After(0.0, (Move(ref('got'), 'got', 'this.delivered'),))),
    )


def deliveries(limit, starts, supply=40.0, horizon=5.0, lanes=2):
    """`starts`: (time, lane, amount, pace). The levels of `delivered` at each hour, and when each
    delivery finished."""
    depot = Template('Depot', stores=(Store('supply', supply, out_capacity=limit),))
    lane = Template(
        'Lane', stores=(Store('delivered', 0.0, tally=True),), events=(delivery(),), links={'depot': 'Depot'}
    )
    engine = Engine([depot, lane], members={'Lane': lanes}, links={('Lane', 'depot'): [0] * lanes}, record=True)
    for at, member, amount, pace in starts:
        engine.start_at(at, 'Lane', 'deliver', member, (amount, pace))
    hours = {}
    for hour in range(1, int(horizon) + 1):
        engine.run(float(hour))
        hours[hour] = [float(engine.read(ref('this.delivered') + newest_got(engine, m), 'Lane', m)) for m in range(lanes)]
    frames = engine.frames[('Lane', 'deliver')]
    return hours, [float(t) for t in frames.c.finished[: frames.c.n]], engine


def newest_got(engine, member):
    """What the newest delivery of a lane holds in its batch now: the litres on their way."""
    frames = engine.frames[('Lane', 'deliver')]
    row = int(frames.newest[member])
    if row < 0 or not frames.c.active[row]:
        return 0.0
    return float(engine.level(getattr(frames.c, 'store:got')[row], engine.now))


# ---- the retirement rule ---------------------------------------------------------------------------


def retirement(wait):
    """20 L enter a batch and leave it at 4 L/h. Without the gate the occurrence ends at 2 h with
    12 L in its batch, and the run stops. With `until batch <= 0 L` it ends at 5 h."""
    steps = [After(0.0, (Move(ref('amount'), 'this.supply', 'batch'),)), After(2.0)]
    if wait:
        steps.append(Until(ref('batch') <= 0.0))
    deliver = Event(
        'deliver',
        params=(('amount', 0.0, 100.0),),
        stores=(Store('batch', 0.0, upper=ref('amount')),),
        flows=(Flow('delivery', 'batch', 'this.water', request=4.0),),
        steps=tuple(steps),
    )
    site = Template('Site', stores=(Store('supply', 50.0), Store('water', 0.0)), events=(deliver,))
    engine = Engine([site])
    engine.start_at(0.0, 'Site', 'deliver', args=(20.0,))
    return engine


# ---- a flow that is starved stays connected --------------------------------------------------------


def starved():
    """A tank with 3 L and a delivery that asks 2 L/h for 4 h. The tank is empty at 1.5 h: the flow
    gets nothing and stays in the collection. At 2 h a second event puts 5 L in, and it runs again."""
    deliver = Event('deliver', flows=(Flow('pipe', 'this.water', SINK, request=2.0),), steps=(After(4.0),))
    top_up = Event('top_up', steps=(After(2.0, (Move(5.0, 'this.reserve', 'this.water'),)),))
    tank = Template('Tank', stores=(Store('water', 3.0), Store('reserve', 5.0)), events=(deliver, top_up))
    engine = Engine([tank])
    engine.start_at(0.0, 'Tank', 'deliver')
    engine.start_at(0.0, 'Tank', 'top_up')
    return engine


# ---- two starts at one time ------------------------------------------------------------------------


def two_starts():
    """Two starts at one time are two occurrences; `.at(t)` gives the one made later."""
    record = Event('record', params=(('amount', 0.0, 100.0),), steps=(After(0.0, (Assign('this.delivered', '+=', ref('amount')),)),))
    tank = Template('Tank', fields={'delivered': 0.0}, events=(record,))
    engine = Engine([tank])
    engine.start_at(1.0, 'Tank', 'record', args=(20.0,))
    engine.start_at(1.0, 'Tank', 'record', args=(5.0,))
    engine.run(2.0)
    return engine


def main():
    rows, _ = flows_table_rows()
    print('Flows created during a run: count(occurrences), count(flows), sum(request), outflow.actual_rate')
    for label, row in zip(('before A', 'A runs', 'A done', 'B runs'), rows):
        print(f'  {label:9s} {row}')
    print('The newest occurrence: (pipe.request, pipe.actual_rate, started, any active)')
    for at, row in frozen_request().items():
        print(f'  t = {at} h: {row}')
    print('A shared limit of 3 L/h, 2 L/h asked by each: (t, the rates of the flows present, the total)')
    for row in shared_limit()[0]:
        print(f'  {row}')
    compared, differ = fresh_formation()
    print(f'  formed fresh from the present members at {compared} random times: {differ} differ bit for bit')
    differ, worst = running_total_drift()
    print(f'  a running float total instead, 10,000 joins and leaves: differs {differ} times, by up to {worst:.3g}')
    for forget in (False, True):
        engine = crossing(forget)
        at, level = engine.read(ref('this.alarm_at'), 'Tank'), engine.read(ref('this.level_at_alarm'), 'Tank')
        print(f'The tank and its alarm at 16 L, forget_membership={forget}: fires at {at:g} h with {level:g} L')
    print(f'  by small steps, with no engine: {crossing_by_small_steps():.3f} h')
    engine = grinder().run(1.0)
    print('The grinder:', float(engine.read(ref('this.beans'), 'Grinder')), 'g after', int(engine.read(count_occ('this.refill'), 'Grinder')), 'refills')
    engine = clock().run(10.0)
    print('The clock: inspections by 10 h =', float(engine.read(ref('this.inspections'), 'Plant')))
    engine = inspect_with_a_delay().run(10.0)
    print('inspect(3 h): stages at', [float(engine.read(ref('this.' + name), 'Plant')) for name in ('first_at', 'second_at', 'noted_at')])
    for label, limit, starts in (
        ('separate supplies (no limit)', INF, [(0.0, 0, 20.0, 10.0), (0.0, 1, 20.0, 10.0)]),
        ('shared limit 10 L/h', 10.0, [(0.0, 0, 20.0, 10.0), (0.0, 1, 20.0, 10.0)]),
        ('shared limit, B starts at 1 h', 10.0, [(0.0, 0, 20.0, 10.0), (1.0, 1, 20.0, 10.0)]),
    ):
        hours, finished, _ = deliveries(limit, starts)
        print(f'Deliveries, {label}: at 1 h {hours[1]}, at 2, 3, 4 h {hours[2]}, {hours[3]}, {hours[4]}; finished {finished}')
    for wait in (True, False):
        try:
            engine = retirement(wait).run(6.0)
            print('Retirement with the gate: finished at', float(engine.frames[('Site', 'deliver')].c.finished[0]), 'h')
        except RunStopped as problem:
            print('Retirement without the gate:', problem)
    engine = starved()
    for at in (1.0, 1.75, 3.0):
        engine.run(at)
        print(f'Starved flow at {at} h: water {float(engine.read(ref("this.water"), "Tank")):g} L, flows {int(engine.read(n_flows("this.water"), "Tank"))}, rate {float(engine.read(actual("this.water"), "Tank")):g} L/h')
    engine = two_starts()
    print('Two starts at 1 h:', int(engine.read(count_occ('this.record'), 'Tank')), 'occurrences,', int(engine.read(count_done('this.record'), 'Tank')), 'done; newest amount', float(engine.read(newest('this.record', 'amount'), 'Tank')), '; delivered', float(engine.read(ref('this.delivered'), 'Tank')), '; since', float(engine.read(since('this.record'), 'Tank')))


if __name__ == '__main__':
    main()
