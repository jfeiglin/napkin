"""A record of some values holds what their keyed reads need (the review of `2cd1751`, R05;
`scratch/rewrite/briefs/audit3b.md` at af5428b, agent V).

The rule (`napkin/program/record.py`, "What a record holds": a record of only some values holds what
their values need, by one function of its request and its trace, for each run's record; spec, "Collections, keys and projections"; D10): a value read from a record of it alone
is the value that a record of every value gives. A keyed read `c.by(f).at(x)` reads the members' keys
`f`, the tests of a `where`, its key `x` and the value of the member that it selects: a record that
keeps a formula over it keeps each of these.

The rule test: random tables of readings (an hour and a factor) and of places (a rank and a base need,
drawn or fixed), a table of tiers by a threshold, and formulas that read them by every form of keyed
read: by a fixed field at the time (`Reading.instances.by(hour).at(t).factor`), at a constant key
(`Place.instances.by(rank).at(1).base_need`), at a store that a flow fills (`.at(tank.level)`), on the
natural keys, after a `where`. Each formula is read from a record of it alone made every way that one
is made: a fresh run of the request, the run store's record of the same request (warm), a
record that a stop at a breakpoint ends, and each sample of `napkin sample`. The expected values are
worked by hand: the member with the greatest key at or below x, the later-created of equal keys
(spec, "c.at(x) reads the member with the greatest key at or below x").
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, replace

import pytest

from napkin import store
from napkin.engine.timeline import read, run
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint
from napkin.program.config import Request
from napkin.program.record import Unavailable
from napkin.session import Session
from tests.commands.call import napkin

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}, 'W': {'energy': 1, 'time': -1}}
PACKAGE_UNITS = {
    'L': {'dimensions': {'volume': 1}, 'scale': 1, 'description': 'A litre.'},
    'W': {'dimensions': {'energy': 1, 'time': -1}, 'scale': 1, 'description': 'A watt.'},
}
HORIZON = 4
TIMES = [0, 0.5, 1, 1.5, 2, 2.5, 3, 4]
STOP = Breakpoint('tank.tick.step[0]')  # at 3 h


@dataclass(frozen=True)
class Case:
    """A random model and, for each formula that reads a keyed read, its value at each time of
    `TIMES` (a number, or None below the first key), and the path of the drawn base that it scales."""

    text: str
    expected: dict
    drawn: dict


def selected(keys, x):
    """The place of the member that `.at(x)` selects: the greatest key at or below x, the later of
    equal keys; None below the first key."""
    best = None
    for place, key in enumerate(keys):
        if key <= x + 1e-12 and (best is None or key >= keys[best]):
            best = place
    return best


def case(seed):
    """The random model of a seed (see the module)."""
    rng = random.Random(seed)
    hours = [0] + [rng.choice([0.5, 1, 1.5, 2, 3]) for _ in range(rng.randint(1, 3))]
    factors = [rng.choice([1, 0.5, 0.25, 2, 0.75]) for _ in hours]
    ranks = [rng.randint(0, 3) for _ in range(rng.randint(2, 3))]
    bases = [rng.randint(2, 9) for _ in ranks]
    drawn = [rng.random() < 0.5 for _ in ranks]
    thresholds = [0, *sorted(rng.sample(range(1, 4), 2))]
    prices = [rng.randint(1, 9) for _ in thresholds]
    fill = rng.choice([0.5, 1])
    key = rng.randint(0, 3)
    natural = rng.randint(0, len(hours) - 1)
    least = rng.choice([0.5, 0.75])
    lines = [
        'scenario "Keyed records"',
        f'    horizon {HORIZON} h',
        '',
        'Reading:',
        '    input hour: h = 0 h',
        '    input factor = 1',
    ]
    for k, (hour, factor) in enumerate(zip(hours, factors)):
        lines += [f'r{k}: Reading', f'    hour = {hour} h', f'    factor = {factor}']
    lines += [
        '',
        'Place:',
        '    input rank = 0',
        '    input base_need: W = 1 W',
        '    need = formula(this.base_need * Reading.instances.by(hour).at(t).factor)',
        f'    filtered = formula(this.base_need * Reading.instances.where(factor >= {least}).by(hour).at(t).factor)',
    ]
    for k, (rank, base, draw) in enumerate(zip(ranks, bases, drawn)):
        given = f'uniform({base - 1} W, {base + 1} W).draw()' if draw else f'{base} W'
        lines += [f'p{k}: Place', f'    rank = {rank}', f'    base_need = {given}']
    lines += ['', 'Tier:', '    input threshold: L = 0 L', '    input price = 1']
    for k, (threshold, price) in enumerate(zip(thresholds, prices)):
        lines += [f'k{k}: Tier', f'    threshold = {threshold} L', f'    price = {price}']
    lines += [
        '',
        'tank:',
        '    level: L = 0 L in [0 L,]',
        '    ticks = 0',
        '    flow fill: SOURCE -> this.level',
        f'        request = {fill} L/h',
        '    tick = event():',
        '        after 3 h:',
        '            this.ticks += 1',
        '',
        f'first = formula(Place.instances.by(rank).at({key}).base_need)',
        'tier = formula(Tier.instances.by(threshold).at(tank.level).price)',
        f'natural = formula(Reading.instances.at({natural}).factor)',
        '',
        'tank.tick.start()',
    ]
    expected, scaled = {}, {}
    for k, base in enumerate(bases):
        place = [selected(hours, t) for t in TIMES]
        expected[f'p{k}.need'] = [None if found is None else base * factors[found] for found in place]
        kept = [j for j, factor in enumerate(factors) if factor >= least]
        within = [selected([hours[j] for j in kept], t) for t in TIMES]
        expected[f'p{k}.filtered'] = [
            None if found is None else base * factors[kept[found]] for found in within
        ]
        if drawn[k]:
            scaled[f'p{k}.need'] = (
                f'p{k}.base_need',
                [None if found is None else factors[found] for found in place],
            )
    rank = selected(ranks, key)
    expected['first'] = [None if rank is None else bases[rank]] * len(TIMES)
    expected['tier'] = [prices[selected(thresholds, fill * t)] for t in TIMES]
    expected['natural'] = [factors[natural]] * len(TIMES)
    # A drawn base is its median in the default run: the middle of its uniform range.
    return Case('\n'.join(lines) + '\n', expected, scaled)


def agrees(found, wanted):
    """A value read against the rule: the number, or below the first key `Unavailable`."""
    if wanted is None:
        return isinstance(found, Unavailable) and 'no member has a key at or below' in found.reason
    return (
        isinstance(found, int | float)
        and not isinstance(found, bool)
        and math.isclose(found, wanted, rel_tol=1e-9)
    )


def check(where, path, values, wanted, times=TIMES):
    """The values of a path read one way, against the values of the rule at the same times."""
    for t, value, expected in zip(times, values, wanted):
        assert agrees(value, expected), f'{where}: {path} at {t} h reads {value!r}, not {expected!r}'


def alone(configuration, program, path, horizon=HORIZON):
    """The configuration whose request names one path."""
    return replace(configuration, request=Request(horizon, everything=False, keys=(key_of(program, path),)))


SEEDS = range(30)


@pytest.mark.parametrize(
    'seed', [*SEEDS[:5], *(pytest.param(seed, marks=pytest.mark.deep) for seed in SEEDS[5:])]
)
def test_a_record_of_a_keyed_read_alone_reads_as_a_record_of_every_value(seed, tmp_path):
    """Each formula over a keyed read, read from a record of every value and from a record of it
    alone: fresh, in the store, ended by a stop at 3 h, the view at
    that stop, and the run resumed from it to its end."""
    made = case(seed)
    c = compile_text(made.text, UNITS)
    program, configuration = c.program, c.configuration
    paths = list(made.expected)
    everything = run(program, configuration)
    for found in read(everything, program, paths, TIMES):
        check('a record of every value', found.path, found.values, made.expected[found.path])
    with store.use(tmp_path / 'store'):
        store.run(program, configuration)
        for path in paths:
            (fresh,) = read(run(program, alone(configuration, program, path)), program, [path], TIMES)
            check('a record of the value alone', path, fresh.values, made.expected[path])
            store.run(program, alone(configuration, program, path))
            (warm,) = read(store.run(program, alone(configuration, program, path)), program, [path], TIMES)
            check('the store, warm', path, warm.values, made.expected[path])
            session = Session(program, alone(configuration, program, path), (STOP,))
            session.advance()
            early = [t for t in TIMES if t <= 3]
            (stopped,) = read(session.checkpoint.record, program, [path], early)
            check('a record that a stop ends', path, stopped.values, made.expected[path], early)
            (shown,) = session.view([path]).values
            check('a view at the stop', path, [shown.value], made.expected[path][TIMES.index(3) :], [3])
            assert session.advance() is None
            (resumed,) = read(session.record, program, [path], TIMES)
            check('a record of a run resumed from its stop', path, resumed.values, made.expected[path])


def capped(*steps):
    """A tank of 10 L whose drain asks half its water an hour, with its outflow capped at 4 L/h (an
    endpoint setting: the set of a rate that moves with one runs on the sparse integrator), a spare
    that a flow fills at 1 L/h, `seen`, a formula of the water, and an event with `steps`, started at
    0 h."""
    from napkin.program.build import (
        SINK,
        SOURCE,
        Builder,
        endpoint,
        event,
        flow,
        formula,
        q,
        start,
        this,
        value,
    )

    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    tank = b.entity(
        'tank',
        value('water', 'L', 10, lower=0, outflow=endpoint(capacity=q(4, 'L/h'))),
        value('spare', 'L', 0, lower=0),
        value('seen', 'L', formula(this.water)),
        flow('drain', this.water, SINK, request=formula(this.water / q(2, 'h'))),
        flow('fill', SOURCE, this.spare, request=q(1, 'L/h')),
        event('swap', *steps),
    )
    b.setup(start(tank.swap))
    return b.finish()


def test_a_record_of_some_keys_of_a_set_on_the_sparse_integrator_reads_as_one_of_every_value():
    """A run of a request of some keys over a set that runs on the sparse integrator keeps what the
    keys need, and only that, as it goes (`Recorder.wanted`, the one rule `needed` as the run goes):
    it raised AttributeError. The tank drains at its cap of 4 L/h to 8 L at 0.5 h, then at half its
    water an hour: 8 e^(-(t - 0.5)/2) L; at 1 h a stage makes `seen` the water plus the spare, which
    fills at 1 L/h, so a record of `seen` alone keeps the spare from then. Worked by hand, and each
    value is what the record of every value of the same run gives."""
    from napkin.program.build import after, assign, formula, q, this
    from napkin.program.config import Configuration
    from napkin.program.record import Key

    program = capped(after(q(1, 'h'), assign(this.seen, formula(this.water + this.spare))))
    times = [0.25, 0.75, 1.5, 3]
    water = [9, *(8 * math.exp(-(t - 0.5) / 2) for t in times[1:])]
    expected = {
        'tank.water': water,
        'tank.drain.actual_rate': [4, *(level / 2 for level in water[1:])],
        'tank.water.outflow.actual_rate': [4, *(level / 2 for level in water[1:])],
        'tank.seen': [level + (t if t >= 1 else 0) for level, t in zip(water, times)],
    }
    everything = run(program, Configuration(Request(4)))
    for path, wanted in expected.items():
        key = Key('tank', tuple(path.split('.')[1:]))
        record = run(program, Configuration(Request(4, everything=False, keys=(key,))))
        assert record.failure is None, record.failure
        (alone,), (whole,) = read(record, program, [path], times), read(everything, program, [path], times)
        assert list(alone.values) == pytest.approx(wanted, rel=1e-6), (path, alone.values)
        assert alone.values == whole.values, path
        kept = {str(history.key) for history in record.histories}
        assert ('tank.spare' in kept) == (path == 'tank.seen'), (path, sorted(kept))


@pytest.mark.parametrize(
    'seed', [*SEEDS[:2], *(pytest.param(seed, marks=pytest.mark.deep) for seed in SEEDS[2:10])]
)
def test_each_sample_of_napkin_sample_reads_a_keyed_read(seed, tmp_path, capsys):
    """`napkin sample --value` records the values that it names alone in each sample: a formula over
    a keyed read has a spread, and in each sample it is its drawn base times the factor of the reading
    that its keyed read selects."""
    made = case(seed)
    folder = tmp_path / 'keyed'
    folder.mkdir()
    (folder / 'model.scn').write_text(made.text, encoding='utf-8')
    (folder / 'units.json').write_text(json.dumps(PACKAGE_UNITS), encoding='utf-8')
    for t in (1, 2.5):
        paths = [*made.expected, *(base for base, _ in made.drawn.values())]
        found = napkin(
            capsys,
            'sample',
            folder,
            '--json',
            '--value',
            ','.join(paths),
            '--at',
            f'{t}h',
            '--samples',
            '3',
            '--jobs',
            '1',
        )
        assert found.code == 0, found.err
        for path in made.expected:
            value = found.doc['values'][path]
            wanted = made.expected[path][TIMES.index(t)]
            assert value['reason'] is None or wanted is None, (
                f'napkin sample: {path} at {t} h: {value["reason"]}'
            )
        for path, (base, factors) in made.drawn.items():
            factor = factors[TIMES.index(t)]
            for sample in found.doc['draws']:
                need, drawn = sample['values'][path], sample['values'][base]
                assert math.isclose(need, drawn * factor, rel_tol=1e-9), (path, t, sample['values'])
