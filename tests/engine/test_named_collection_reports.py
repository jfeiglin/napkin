"""A named collection is the collection that it names, in a report too (the readiness audit of
`8b3a01a`, row 15; `briefs/audit3.md`, agent E's finding for R).

`tanks = Tank.instances` at the top level, then `total = formula(sum(tanks.water))`: the proof that
the total never falls read `tanks` as a value, so its lag was refused ("a setting or a property of a
value") where the same over `Tank.instances` lags, and its evidence trail listed `total` alone. The
same held for a collection local of an event. The rule (spec, "Collections, keys and projections": a
binding names a collection, and a path that steps into it reads its init): every read of a report
over a named collection is the read over the collection written in its place, so its lag holds or is
refused alike, with the same values, and its trail lists the same parts, exercised alike.

The rule test: random tanks that fill or drain at their own rates, a named collection of them at the
top level, in an entity and in an event (an instances, a literal, a `where` on an input, a `by` read at
a key), a random read of it (`sum`, `min`, `max`, `count`, a keyed read); each run straight on, and
stopped at a stage where an edit lowers or raises a tank. The lag of the read and its trail, named and
written in place, agree. The expected proofs are worked by hand: a total of tanks that only fill never
falls, nor does a count, and one that a drain or an edit that lowers a tank empties can fall.
"""

from __future__ import annotations

import random
import textwrap

import pytest

from napkin.engine.report import Lag, report
from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint
from napkin.program.record import Key, Unavailable

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
TIMES = [1.5, 2, 3, 4]
LAG = Lag(0.5, 1)


def tanks(rng):
    """The tanks t0 ... t{n-1}: (rank, full, water in L, fill in L/h, drain in L/h)."""
    found = []
    for _ in range(rng.randint(1, 4)):
        fill, drain = rng.choice([0, 1, 2]), rng.choice([0, 0, 0.5])
        found.append((rng.randint(1, 3), rng.random() < 0.5, rng.randint(2, 9), fill, drain))
    return found


def collection(rng, n):
    """A collection of the tanks, written in place."""
    form = rng.choice(['instances', 'literal', 'where', 'where full'])
    if form == 'instances':
        return 'Tank.instances'
    if form == 'literal':
        return '<' + ', '.join(f't{k}' for k in sorted(rng.sample(range(n), rng.randint(1, n)))) + '>'
    if form == 'where':
        return f'Tank.instances.where(rank >= {rng.randint(1, 3)})'
    return 'Tank.instances.where(full)'


def reading(rng):
    """A read of a collection C."""
    op = rng.choice(['sum', 'min', 'max', 'count', 'at', 'sum where'])
    if op in ('sum', 'min', 'max'):
        return f'{op}(C.water)'
    if op == 'count':
        return 'count(C)'
    if op == 'at':
        return f'C.by(rank).at({rng.choice([1, 2, 3])}).water'
    return f'sum(C.where(rank >= {rng.randint(1, 3)}).water)'


def model(data, where, read_text, collection_text, named):
    """The model's text: the tanks, a stage of `crew` at 1 h (where a breakpoint can stop the run),
    and the read at a place (`top`, `entity`, `event`), over the named collection or the collection
    in its place; and the path of the read."""
    rows = []
    for k, (rank, full, water, fill, drain) in enumerate(data):
        rows += [f't{k}: Tank', f'    rank = {rank}', f'    full = {"true" if full else "false"}']
        rows += [f'    water = {water} L', f'    fill = {fill} L/h', f'    drain = {drain} L/h']
    name = {'top': 'tanks', 'entity': 'this.tanks', 'event': 'tanks'}[where]
    read = read_text.replace('C', name if named else collection_text)
    lines = [
        'scenario "Named"',
        '    horizon 4 h',
        '',
        'Tank:',
        '    input rank = 1',
        '    input full: bool = false',
        '    input fill: L/h = 0 L/h',
        '    input drain: L/h = 0 L/h',
        '    water: L = 1 L in [0,]',
        '    flow filling: SOURCE -> this.water',
        '        request = this.fill',
    ]
    if any(drain for *_, drain in data):
        # A flow that drains a tank can take from what a total counts, whatever its rate.
        lines += ['    flow draining: this.water -> SINK', '        request = this.drain']
    lines += [
        '',
        *rows,
        '',
        'crew:',
        '    tick = event():',
        '        after 1 h',
    ]
    if where == 'entity':
        lines += [f'    tanks = {collection_text}'] if named else []
        lines += [f'    total = formula({read})']
        path = 'crew.total'
    if where == 'event':
        lines += ['    look = event():']
        lines += [f'        tanks = {collection_text}'] if named else []
        lines += [f'        total = formula({read})', '        after 4 h']
        path = 'crew.look#0.total'
    lines += ['', 'crew.tick.start()']
    lines += ['crew.look.start()'] if where == 'event' else []
    if where == 'top':
        lines += [f'tanks = {collection_text}'] if named else []
        lines += [f'total = formula({read})']
        path = 'total'
    return textwrap.dedent('\n'.join(lines)) + '\n', path


def reported(text, path, edit):
    """The report of the read with its lag, and of it alone with its trail: (whether the lag
    holds, its values, the trail); or (`failed`, its time) for a run that fails (a formula of an
    occurrence that cannot be evaluated at its entry: `min` of no tank, a key below every member's).
    `edit` is (tank, new water in L) made at the stop before the tick's stage at 1 h, or None for a
    run straight on."""
    found = compile_text(text, UNITS)
    program, configuration = found.program, found.configuration
    made = Run(Plan.of(program, configuration), (Breakpoint('crew.tick.step[0]'),) if edit else ())
    record = made.run()
    if edit is not None:
        assert isinstance(record, Checkpoint)
        made.edit(Key(f't{edit[0]}', ('water',)), edit[1])
        record = made.resume()
    if record.failure is not None:
        return 'failed', float(record.failure.t)
    lagged = report(record, program, configuration, [path], TIMES, lags={path: LAG}).values[0]
    plain = report(record, program, configuration, [path], TIMES).values[0]
    trail = tuple((used.kind, used.origin, used.owner, used.exercised) for used in plain.trail)
    return lagged.lag is not None, lagged.values, trail


def same(left, right):
    if isinstance(left, Unavailable) or isinstance(right, Unavailable):
        return isinstance(left, Unavailable) and isinstance(right, Unavailable)
    return left == pytest.approx(right, rel=1e-12, abs=1e-12)


@pytest.mark.parametrize('where', ['top', 'entity', 'event'])
@pytest.mark.parametrize('seed', range(10))
def test_a_report_over_a_named_collection_is_the_report_over_the_collection_in_its_place(where, seed):
    rng = random.Random(f'{where} {seed}')
    data = tanks(rng)
    collection_text = collection(rng, len(data))
    read_text = reading(rng)
    edit = None if rng.random() < 0.5 else (rng.randrange(len(data)), rng.choice([0, 1, 9]))
    named = reported(*model(data, where, read_text, collection_text, True), edit)
    written = reported(*model(data, where, read_text, collection_text, False), edit)
    if 'failed' in (named[0], written[0]):
        assert named == written
        return
    assert named[0] == written[0], (named, written)
    assert all(same(a, b) for a, b in zip(named[1], written[1], strict=True)), (named, written)
    assert named[2] == written[2]


@pytest.mark.parametrize('where', ['top', 'entity', 'event'])
def test_a_total_of_tanks_that_only_fill_lags_over_a_named_collection(where):
    """By hand: t0 and t1 hold 2 L and 3 L and fill at 1 L/h each, and nothing drains them, so the
    total is 5 L + 2t L/h, which never falls (each fill only adds to what it counts); its lag from
    0.5 h to 1 h at 2 h is its mean over [1 h, 1.5 h], 7.5 L. Its trail holds each tank's fill and
    water, exercised. An edit that lowers t0 from 3 L to 1 L at the stop at 1 h withdraws the proof,
    named or in place, and the values are the plain read: 3 L + 2t L/h from 1 h, so 7 L at 2 h."""
    data = [(1, False, 2, 1, 0), (1, False, 3, 1, 0)]
    for edit, holds, value in ((None, True, 7.5), ((0, 1), False, 7.0)):
        for named in (True, False):
            text, path = model(data, where, 'sum(C.water)', 'Tank.instances', named)
            lag, values, trail = reported(text, path, edit)
            assert lag is holds, (named, edit)
            assert values[1] == pytest.approx(value), (named, edit)
            parts = {(kind, origin, owner) for kind, origin, owner, exercised in trail if exercised}
            assert {('flow', 'Tank.filling', 't0'), ('value', 'Tank.water', 't1')} <= parts, trail
