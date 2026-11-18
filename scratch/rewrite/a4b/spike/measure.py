"""The cost of members that come and go (brief A4b, "Cost").

`lanes` lanes each repeat a delivery from one shared depot: every delivery owns a batch `got`
and one flow `pipe` from `depot.supply` to its batch, at `pace` 1 L/h; it waits until its batch
is full, moves the batch to the tally of its lane, and starts the next delivery of its lane. So
`lanes` occurrences are alive at a time, and `lanes * per_lane` start and finish in the run. The
supply has a limit on its outflow: either far above the requests (not binding) or half of them
(binding: then every join and every leave changes the rate of every flow at the depot, and so the
prediction of every batch and every gate).

    python measure.py            # the table of FINDINGS.md: 1,000 lanes x 100, best of three
    python measure.py --scale    # also 10, 100, 1,000 and 10,000 alive, 20,000 starts each

The cost of a start is the time in `Engine.start` (the frame, its batch, its flow joining both
endpoints); of a finish, the time in `Engine.finish` (the flow leaving, the retirement check, the
record). The predictions made again are counted by the engine (`predictions: ...`) and timed as
the sharing pass and the reading of the gates (`spent['network']`, `spent['conditions']`).
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Engine  # noqa: E402
from expr import ref  # noqa: E402
from program import After, Event, Flow, Move, Start, Store, Template, Until  # noqa: E402


def program(limit):
    deliver = Event(
        'deliver',
        params=(('amount', 0.0, 1e9), ('pace', 0.0, 1e9), ('left', 0.0, 1e9)),
        stores=(Store('got', 0.0, upper=ref('amount')),),
        flows=(Flow('pipe', 'this.depot.supply', 'got', request=ref('pace')),),
        steps=(
            Until(ref('got') >= ref('amount')),
            After(0.0, (Move(ref('got'), 'got', 'this.delivered'),)),
            After(0.0, (Start('this.deliver', (ref('amount'), ref('pace'), ref('left') - 1.0)),), guard=ref('left') >= 1.0),
        ),
    )
    depot = Template('Depot', stores=(Store('supply', 1e12, out_capacity=limit),))
    lane = Template('Lane', stores=(Store('delivered', 0.0, tally=True),), events=(deliver,), links={'depot': 'Depot'})
    return depot, lane


def one_run(lanes, per_lane, binding, seed=1):
    limit = 0.5 * lanes if binding else 1e3 * lanes
    depot, lane = program(limit)
    engine = Engine(
        [depot, lane],
        members={'Lane': lanes},
        links={('Lane', 'depot'): [0] * lanes},
        timing=True,
        max_occurrences=10 * lanes * per_lane,
        max_active=10 * lanes,
    )
    spent = {'start': 0.0, 'finish': 0.0}
    for name in spent:
        method = getattr(engine, name)

        def timed(*args, _method=method, _name=name):
            tick = time.perf_counter()
            _method(*args)
            spent[_name] += time.perf_counter() - tick

        setattr(engine, name, timed)
    rng = np.random.default_rng(seed)
    for member in range(lanes):
        engine.start_at(float(rng.uniform(0.0, 1.0)), 'Lane', 'deliver', member, (float(rng.uniform(0.5, 1.5)), 1.0, per_lane - 1.0))
    tick = time.perf_counter()
    engine.run(1e9)
    wall = time.perf_counter() - tick
    frames = engine.frames[('Lane', 'deliver')]
    starts, finishes = engine.count['starts'], engine.count['finishes']
    assert starts == finishes == lanes * per_lane, (starts, finishes)
    made_again = sum(value for key, value in engine.count.items() if key.startswith('predictions: '))
    return {
        'wall': wall,
        'start': spent['start'] / starts,
        'finish': spent['finish'] / finishes,
        'network': engine.spent['network'],
        'conditions': engine.spent['conditions'],
        'commit': engine.spent['commit'],
        'made_again': made_again,
        'per_change': made_again / (starts + finishes),
        'rates': engine.count['rates made again'],
        'moments': engine.count['moments'],
        'rounds': engine.count['rounds'],
        'entries': engine.count['timeline entries'],
        'bytes': (frames.c.nbytes()) / frames.c.n,
        'starts': starts,
    }


def best_of(runs, lanes, per_lane, binding):
    found = [one_run(lanes, per_lane, binding) for _ in range(runs)]
    return min(found, key=lambda row: row['wall'])


def show(label, row):
    us = 1e6
    print(
        f'| {label} | {row["starts"]:,} | {row["wall"]:.2f} s | {row["start"] * us:.1f} us | {row["finish"] * us:.1f} us '
        f'| {row["network"]:.2f} s | {row["conditions"]:.2f} s | {row["made_again"]:,} ({row["per_change"]:.1f} per change) '
        f'| {row["rates"]:,} | {row["moments"]:,} | {row["entries"]:,} | {row["bytes"]:.0f} B |'
    )


def main():
    print('load:', os.popen('uptime').read().strip())
    print(
        '| case | starts | run | a start | a finish | sharing and restarts | gates | predictions made again '
        '| rates made again | moments | timeline entries | pool bytes per occurrence |'
    )
    print('| - | -: | -: | -: | -: | -: | -: | -: | -: | -: | -: | -: |')
    for binding in (False, True):
        show(f'1,000 alive, limit {"binding" if binding else "not binding"}', best_of(3, 1000, 100, binding))
    if '--scale' in sys.argv:
        for lanes in (10, 100, 1000, 10000):
            for binding in (False, True):
                show(f'{lanes:,} alive, {"binding" if binding else "not binding"}', best_of(1, lanes, max(1, 20000 // lanes), binding))
    print('load:', os.popen('uptime').read().strip())


if __name__ == '__main__':
    main()
