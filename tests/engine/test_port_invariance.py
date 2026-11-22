"""Compare physical readings and original event order under each port-readiness transformation."""

from collections import defaultdict
from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import zip_longest
from unittest.mock import patch

import pytest

from napkin.engine.timeline import Plan, Run, read, resume, stocks
from napkin.program.artifact import loads as load_artifact
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.config import Configuration, Request
from napkin.program.record import Key, Unavailable
from tests.engine.port_cases import HORIZON, Case, Spelling, builder_program, text_program
from tests.reference.evaluate import label
from tests.reference.from_program import run_of, scale_at, value_at, values_at

CONFIG = Configuration(Request(HORIZON))
# `roundoff` moves every ledger read that a decision makes two places each way
# (`stocks.LEDGER_PROBE`): a decision that changes under it depends on the platform.
TRANSFORMS = (
    'empty_event',
    'named',
    'small_unit',
    'split',
    'builder',
    'artifact',
    'checkpoint',
    'sparse',
    'roundoff',
)
GUARD = 'plant.observe.step[0]'

# physical scale in litres or litres/hour, and the multiplier on the declared tolerance.
# projected = delivered / 4 h inherits the integrated reading's allowance, divided by 4 h.
READS = {
    'delivered': (1, 10),
    'tap.request': (1, 2),
    'tap.actual_rate': (1, 2),
    'projected': (0.25, 10),
    'ramp.actual_rate': (1, 2),
    'basin': (1, 10),
    'refund': (1, 10),
    'paid': (1, 10),
    'saved': (1, 10),
    'cash': (1, 10),
    'bulk': (1, 10),
    'work#0.batch': (1, 10),
    'work#0.done': None,
    'marked': None,
}


def path_key(path):
    if path.startswith('work#0.'):
        return Key('plant.work#0', (path.split('.')[1],))
    return Key('plant', tuple(path.split('.')))


KEYS = {name: path_key(name) for name in READS}


@dataclass(frozen=True)
class Stage:
    kind: str
    owner: str
    origin: str
    round: int
    ran: bool | None = None
    tie: object = None


@dataclass
class View:
    values: dict
    stages: dict
    moves: dict
    flows: dict
    outcome: tuple


def times_for(case):
    # Either switch side is far beyond the model's 1e-8 h locator error.
    return sorted(
        {
            Fraction(0),
            case.opening - Fraction(1, 128),
            case.opening + Fraction(1, 128),
            Fraction(7, 8),
            Fraction(1),
            Fraction(3, 2),
            Fraction(HORIZON),
        }
    )


def stage_entry(kind, owner, origin, round_, tie=None):
    if owner.startswith('plant.idle#') or kind not in ('start', 'commit', 'finish', 'skip', 'fire'):
        return None
    if origin == GUARD and kind in ('commit', 'skip'):
        return Stage('decision', owner, origin, round_, kind == 'commit', tie)
    return Stage(kind, owner, origin, round_)


def oracle_view(case, program):
    oracle, error = run_of(program, CONFIG)
    # Every generated case has a covered solution and finishes -- NotCovered is a generator defect.
    assert error is None and oracle.view.t == HORIZON, error
    times = times_for(case)
    values = {at: {} for at in times}
    expected = values_at(oracle, program, KEYS.values(), times)
    for name, key in KEYS.items():
        scale = scale_at(program, key)
        for at, raw in zip(times, expected[key], strict=True):
            values[at][name] = raw if isinstance(raw, bool) else scale * raw
    stages = defaultdict(list)
    for entry in oracle.trace:
        kind = {'done': 'finish', 'stage': 'commit'}.get(entry.kind, entry.kind)
        # The interpreter labels a firing with receiver.event.when[k]; the engine carries the receiver separately.
        owner = entry.label.rsplit('.', 2)[0] if kind == 'fire' else entry.label
        stage = stage_entry(kind, owner, entry.origin, entry.round)
        if stage:
            stages[entry.t].append(stage)
    moves = defaultdict(lambda: defaultdict(int))
    flows = defaultdict(lambda: defaultdict(int))
    authored_moves = iter(entry for entry in oracle.trace if entry.kind == 'move')
    for kind, *args in oracle.ledger:
        if kind == 'move':
            at, source, destination, amount = args
            entry = next(authored_moves)
            assert entry.t == at
            stage = entry.origin.rsplit('.do[', 1)[0]
            moves[at][stage, label(source), label(destination)] += amount
        elif kind == 'flow':
            begin, end, leg, _, _, amount = args
            # 1 h (the refund stage) divides two common windows, including under an empty event.
            window = 1 if end <= 1 else HORIZON
            assert window == 1 or begin >= 1
            flows[window][leg] += amount
    for window in (1, HORIZON):
        for leg in ('plant.tap', 'plant.ramp'):
            flows[window].setdefault(leg, 0)  # the oracle omits a closed leg
    return View(values, stages, moves, flows, (HORIZON, 'finished'))


def engine_view(case, program, checkpoint, sparse):
    stops = (Breakpoint('plant.work.step[1]'),) if checkpoint else ()
    machine = Run(Plan.of(program, CONFIG), stops)
    ways = {flow: group.way for group in machine.plan.sets for flow in group.flows}
    assert ways == dict.fromkeys(('plant.tap', 'plant.ramp'), 'sparse' if sparse else 'component'), ways
    rec = machine.run()
    if isinstance(rec, Checkpoint):
        assert checkpoint
        rec = resume(program, loads(dumps(rec)))
    elif checkpoint and not rec.failure:
        pytest.fail('the scheduled checkpoint was never reached')
    times = [at for at in times_for(case) if at <= rec.end]
    values = {at: {} for at in times}
    rows = read(rec, program, list(KEYS.values()), list(map(float, times)))
    for (name, key), row in zip(KEYS.items(), rows, strict=True):
        scale = float(scale_at(program, key))
        for at, val in zip(times, row.values, strict=True):
            values[at][name] = val if isinstance(val, (bool, Unavailable)) else val * scale
    stages = defaultdict(list)
    moves = defaultdict(lambda: defaultdict(int))
    for entry in rec.trace:
        if entry.kind == 'move':
            origin = entry.part.rsplit('.do[', 1)[0]
            moves[entry.t][origin, entry.detail('source'), entry.detail('destination')] += entry.detail(
                'amount'
            )
        stage = stage_entry(entry.kind, entry.owner, entry.part, entry.round, entry.detail('near'))
        if stage:
            # A false guard outside its comparison band does not write a trace entry. The finish
            # of this one-stage occurrence still establishes the decision and its original order.
            if (
                entry.kind == 'finish'
                and entry.owner == 'plant.observe#0'
                and not any(s.origin == GUARD for s in stages[entry.t])
            ):
                stages[entry.t].append(Stage('decision', entry.owner, GUARD, entry.round, False))
            stages[entry.t].append(stage)
    # The tap is the only leg of delivered. The ramp is the only flow into basin, whose entire
    # small receipt is moved into refund at the boundary. These are stock-side, accepted amounts,
    # independent of the published rate and observable without a per-step history in production.
    flows = {}
    if 1 in values:
        flows[1] = {'plant.tap': values[1]['delivered'], 'plant.ramp': values[1]['refund']}
    if HORIZON in values:
        flows[HORIZON] = {
            'plant.tap': values[HORIZON]['delivered'] - values[1]['delivered'],
            'plant.ramp': values[HORIZON]['basin'],
        }
    outcome = (rec.end, 'finished' if rec.failure is None else rec.failure.detail('message'))
    return View(values, stages, moves, flows, outcome)


def numeric(actual, expected, scale, multiplier, where):
    tolerance = CONFIG.numerics.atol_factor * scale + CONFIG.numerics.rtol * abs(expected)
    assert not isinstance(actual, Unavailable), (where, actual, expected)
    assert abs(actual - expected) <= multiplier * tolerance, (where, actual, expected, multiplier * tolerance)


def compare_amounts(ours, theirs, kind, where):
    assert ours.keys() == theirs.keys(), (where, ours, theirs)
    for leg, expected in theirs.items():
        # The model moves whole stocks on these three legs. Splitting a whole-stock
        # move into two statements in one stage keeps the same aggregate allowance.
        level_derived = kind == 'flows' or leg[1:] in {
            ('plant.work#0.batch', 'plant.bulk'),
            ('plant.bulk', 'plant.paid'),
            ('plant.basin', 'plant.refund'),
        }
        numeric(ours[leg], expected, 1, 10 if level_derived else 2, (*where, leg))


def compare(result, reference, seed, transform):
    crossing = CONFIG.numerics.crossing
    cutoff = min(result.outcome[0], reference.outcome[0])

    def moments(view):
        observed = set(view.values) | set(view.stages) | set(view.moves) | set(view.flows)
        return sorted(t for t in observed if t <= cutoff + crossing)

    for ours_at, at in zip_longest(moments(result), moments(reference)):
        where = (seed, transform, at)
        assert ours_at is not None and at is not None and abs(ours_at - at) <= crossing, (
            where,
            'moment time',
            ours_at,
            at,
            crossing,
        )
        committed = set()
        for actual, expected in zip_longest(result.stages.get(ours_at, ()), reference.stages.get(at, ())):
            if (
                actual
                and expected
                and actual.kind == expected.kind == 'decision'
                and replace(actual, tie=None, ran=None) == replace(expected, tie=None, ran=None)
                and actual.ran != expected.ran
                and (actual.tie or expected.tie)
            ):
                # A decision may diverge only on recorded evidence at this point. Earlier
                # stages at the very same time have already committed their transfers.
                ours = {k: v for k, v in result.moves.get(ours_at, {}).items() if k[0] in committed}
                theirs = {k: v for k, v in reference.moves.get(at, {}).items() if k[0] in committed}
                compare_amounts(ours, theirs, 'moves', (*where, 'earlier stage moves'))
                return (*where, actual.origin, actual.ran, expected.ran, actual.tie, expected.tie)
            assert actual and expected and replace(actual, tie=None) == replace(expected, tie=None), (
                where,
                'event order',
                actual,
                expected,
            )
            if actual.kind == 'commit' or actual.ran:
                committed.add(actual.origin)
        for attr in ('moves', 'flows'):
            ours, theirs = getattr(result, attr).get(ours_at, {}), getattr(reference, attr).get(at, {})
            compare_amounts(ours, theirs, attr, (*where, attr))
        for name, expected in reference.values.get(at, {}).items():
            actual = result.values[ours_at][name]
            if READS[name] is None or (name in ('bulk', 'work#0.batch') and at >= 1):
                assert actual == expected, (where, name, actual, expected)
            else:
                numeric(actual, expected, *READS[name], (*where, name))
    assert (
        result.outcome[1] == reference.outcome[1]
        and abs(result.outcome[0] - reference.outcome[0]) <= crossing
    ), (
        seed,
        transform,
        'outcome',
        result.outcome,
        reference.outcome,
    )
    return None


def check_seed(seed, transforms, record_property):
    case = Case.of(seed)
    original = text_program(case, Spelling())
    expected = oracle_view(case, original.program)
    original_view = engine_view(case, original.program, checkpoint=False, sparse=False)
    base_tie = compare(original_view, expected, seed, 'original vs reference')
    for name in transforms:
        spelling = Spelling(**{name: True}) if name in Spelling.__dataclass_fields__ else Spelling()
        if name in ('sparse', 'roundoff'):
            candidate = original.program
        elif name == 'builder':
            candidate = builder_program(case, spelling)
        elif name == 'artifact':
            candidate = load_artifact(original.artifact().data()).program
        elif name == 'checkpoint':
            candidate = original.program
        else:
            candidate = text_program(case, spelling).program
        for probe in (-2, 2) if name == 'roundoff' else (0,):
            label = f'{name} {probe:+d}' if probe else name
            with (
                patch('napkin.engine.timeline.plan.LIMIT', 0 if name == 'sparse' else 150),
                patch.object(stocks, 'LEDGER_PROBE', probe),
            ):
                changed = engine_view(
                    case, candidate, checkpoint=name == 'checkpoint', sparse=name == 'sparse'
                )
            oracle_tie = compare(changed, expected, seed, label + ' vs reference')
            pair_tie = compare(changed, original_view, seed, label + ' vs original')
            if base_tie or oracle_tie or pair_tie:
                record_property(f'near-tie-{label}', repr((seed, base_tie, oracle_tie, pair_tie)))


@pytest.mark.parametrize('seed', range(300))
def test_port_transform(seed, record_property):
    check_seed(seed, (TRANSFORMS[seed % len(TRANSFORMS)],), record_property)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(2000))
def test_all_port_transforms(seed, record_property):
    check_seed(seed, TRANSFORMS, record_property)


def test_only_a_flagged_decision_can_end_a_pair_and_prior_moves_still_count():
    prior = Stage('commit', 'plant.pay#0', 'plant.pay.step[0]', 1)
    guard = Stage('decision', 'plant.observe#0', GUARD, 2, True)
    error = {'delivered': 999}
    leg = (prior.origin, 'plant.cash', 'plant.paid')
    earlier = {1: {leg: 4}}
    expected = View({2: {'delivered': 0}}, {1: [prior, guard]}, earlier, {}, (2, 'finished'))
    actual = View({2: error}, {1: [prior, replace(guard, ran=False)]}, earlier, {}, (2, 'finished'))
    with pytest.raises(AssertionError, match='event order'):
        compare(actual, expected, 1, 'control')
    actual.stages[1][-1] = replace(guard, ran=False, tie=('threshold', 0, 1e-9))
    assert compare(actual, expected, 1, 'control')[:4] == (1, 'control', 1, GUARD)
    actual.moves = {1: {leg: 3}}
    with pytest.raises(AssertionError, match='earlier stage moves'):
        compare(actual, expected, 1, 'control')


def test_a_move_computed_from_a_level_inherits_the_levels_tolerance():
    literal = ('plant.refund_batch.step[0]', 'plant.basin', 'plant.parked')
    stock = ('plant.refund_batch.step[0]', 'plant.basin', 'plant.refund')
    tolerance = CONFIG.numerics.atol_factor + CONFIG.numerics.rtol
    compare_amounts({stock: 1 + 6 * tolerance}, {stock: 1}, 'moves', ('stock move',))
    with pytest.raises(AssertionError, match='literal move'):
        compare_amounts({literal: 1 + 6 * tolerance}, {literal: 1}, 'moves', ('literal move',))
    with pytest.raises(AssertionError, match='stock move'):
        compare_amounts({stock: 1 + 12 * tolerance}, {stock: 1}, 'moves', ('stock move',))


@pytest.mark.parametrize('cap', [False, True])
@pytest.mark.parametrize('named', [False, True])
def test_unit_respellings_keep_every_generated_named_values_own_scale(cap, named):
    case = replace(Case.of(0), hard_cap=cap)
    config = Configuration(Request(0.125))
    versions = []
    for small_unit in (False, True):
        spelling = Spelling(small_unit=small_unit, named=named)
        for program in (text_program(case, spelling).program, builder_program(case, spelling)):
            run = Run(Plan.of(program, config))
            assert run.run().failure is None
            versions.append({name: run.own_scale(name) for name in run.plan.values})
    for observed in versions[1:]:
        assert observed == versions[0]


def test_batched_oracle_reads_preserve_units_occurrences_booleans_and_query_order():
    case = Case.of(9)
    program = text_program(case, Spelling(small_unit=True)).program
    oracle, error = run_of(program, CONFIG)
    assert error is None
    keys = list(reversed(KEYS.values()))
    times = (Fraction(2), case.opening - Fraction(1, 128), Fraction(1), Fraction(1), Fraction(0))
    expected = {key: [value_at(oracle, program, key, t) for t in times] for key in keys}
    assert values_at(oracle, program, keys, times) == expected
    assert oracle.view.t == HORIZON
