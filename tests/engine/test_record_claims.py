"""What a record holds, and what a report claims from it (the re-audit of `0f78c65`, part C of
`scratch/rewrite/briefs/audit2.md`): each cause by the rule that would have caught every instance, on
many random programs, then the re-audit's rows as plain tests. No expected value comes from the
oracle: each is a rule of the spec, a number worked by hand, or the same run read two ways.

- A reader gives a value only from what the record holds, else `Unavailable` with the reason; a cut of
  a stored record answers as a fresh run of the narrower request; the books of a store keep its
  ledger whatever the request names (11).
- A value is read at its own time: permuting the times permutes the values (10).
- The proofs of an edited run follow from its edits: no proof that a report gives is contradicted by
  the run's own values (09).
- A trail says exercised for what an evaluation read, and not for a side that it did not take or a
  case after the one that applied (16).
- Only a number is lagged (21); the budget of pieces holds (18); the reader needs no recursion (15).
"""

from __future__ import annotations

import random
from itertools import pairwise

import pytest

from napkin import store
from napkin.engine.report import Lag, report
from napkin.engine.timeline import Plan, Run, read, run
from napkin.program.build import (
    BOOL,
    SOURCE,
    TEXT,
    Builder,
    add,
    after,
    event,
    fmax,
    fmin,
    formula,
    fsum,
    group_of,
    ifelse,
    input_,
    literal,
    move,
    named,
    q,
    rating,
    reset_when,
    start,
    status,
    t,
    this,
    value,
    when,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint
from napkin.program.config import Configuration, Request
from napkin.program.record import Key, Unavailable
from tests.engine.test_checkpoints import SCENARIOS

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
SEEDS = range(40)


def edited(program, configuration, breakpoints=(), edits=()):
    """The record of a run stopped at each hit of `breakpoints`, edited there by `edits` (target,
    value) at the first stop, and resumed to its end."""
    made = Run(Plan.of(program, configuration), breakpoints)
    found = made.run()
    first = True
    while isinstance(found, Checkpoint):
        if first:
            for target, new in edits:
                made.edit(target, new)
            first = False
        found = made.resume()
    return found


def same(left, right):
    """Two values of one key read two ways: the same yes/no, text or reason, or numbers within the
    roundoff of the run."""
    if isinstance(left, (bool, str, Unavailable)) or isinstance(right, (bool, str, Unavailable)):
        return left == right
    return left == pytest.approx(right, rel=1e-12, abs=1e-12)


# ---- 11. a value comes only from what the record holds ----------------------------------------------


def plant(rng):
    """A random plant: three tanks with random starts, a fill, two pipes of random rates between
    random tanks, a tally of what one pipe gives, two formulas (a sum and a choice on a yes/no), and a
    tick at 1 h, where a breakpoint stops the run; and a random edit there: a tank lowered or raised
    (within its bounds), or the yes/no turned on, or none."""
    b = Builder(UNITS)
    tanks = [value(f'w{k}', 'L', rng.randint(4, 12), lower=0) for k in range(3)]
    pipes = []
    for j in range(2):
        a, c = rng.sample(range(3), 2)
        rate = rng.choice([0.5, 1, 2])
        pipes.append(flow_of(f'p{j}', f'w{a}', f'w{c}', rate))
    keep = [flow_of(f'keep{k}', None, f'w{k}', 0) for k in range(3)]  # each tank is a store
    b.entity(
        'plant',
        *tanks,
        *keep,
        value('open', BOOL, False),
        value('ticks', '', 0),
        value('total', 'L', formula(this.w0 + this.w1 + this.w2)),
        value('pick', 'L', formula(ifelse(this.open, this.w0, this.w2))),
        flow_of('fill', None, 'w0', 1),
        *pipes,
        event('tick', after(q(1, 'h'), add(this.ticks, 1)), after(q(1, 'h'), add(this.ticks, 1))),
    )
    b.setup(start(named('plant').tick))
    program = b.finish()
    edit = rng.choice(['lower', 'raise', 'open', 'none'])
    tank = f'plant.w{rng.randrange(3)}'
    edits = {
        'lower': ((tank, 0.5),),
        'raise': ((tank, 30),),
        'open': (('plant.open', True),),
        'none': (),
    }[edit]
    return program, edits


def flow_of(name, source, sink, rate):
    """A flow of `rate` L/h from the tank `source` (SOURCE for None) to the tank `sink`."""
    from napkin.program.build import flow

    ends = [SOURCE if source is None else getattr(this, source), getattr(this, sink)]
    return flow(name, *ends, request=q(rate, 'L/h'))


PATHS = [
    'plant.w0',
    'plant.w1',
    'plant.w2',
    'plant.total',
    'plant.pick',
    'plant.open',
    'plant.w0.external',
    'plant.w1.external',
    'plant.w2.external',
    'plant.p0.actual_rate',
    'plant.fill.actual_rate',
]


@pytest.mark.parametrize('seed', SEEDS)
def test_a_narrow_record_fresh_or_cut_agrees_with_the_full_one_and_holds_nothing_else(seed):
    """A fresh run of a random request, the same request served from the full record (`store.served`),
    and the full record give the same value of every path that the request holds (a store's ledger with
    the store), at every time; the narrow records give no value of any other path: each is unavailable
    with the reason. The run is edited at its stop at 1 h, so a ledger of an edited store is -1 L, or
    +x L, in all three, whatever the request names."""
    rng = random.Random(seed)
    program, edits = plant(rng)
    stop = (Breakpoint('plant.tick.step[1]'),)
    full = edited(program, Configuration(Request(3)), stop, edits)
    keys = tuple(sorted({Key('plant', tuple(path.split('.')[1:])) for path in rng.sample(PATHS, 3)}, key=str))
    narrow = Request(3, everything=False, keys=keys)
    fresh = edited(program, Configuration(narrow), stop, edits)
    cut = store.served(full, narrow)
    times = sorted({0, 0.5, 1, 1.5, 2, 3, *(round(rng.uniform(0, 3), 3) for _ in range(3))})
    held = {str(key) for key in keys} | {f'{key}.external' for key in keys if len(key.steps) == 1}
    for path in PATHS:
        (whole,) = read(full, program, [path], times)
        for record in (fresh, cut):
            (found,) = read(record, program, [path], times)
            for at, value_, expected in zip(times, found.values, whole.values, strict=True):
                if path in held:
                    assert same(value_, expected), (seed, path, at, value_, expected)
                else:
                    assert isinstance(value_, Unavailable), (seed, path, at, value_)
                    assert value_.reason.startswith(f'the record holds no value of {path}')


def test_a_ledger_reads_the_books_of_the_store_whatever_the_request_names():
    """Row 11: the family's tank holds 6 L at 2 h and an edit lowers it to 5 L, a withdrawal of 1 L.
    Recording the stock alone, the ledger alone or both, or serving the stock from a stored full run,
    the ledger reads 0 L at 1 h and -1 L at 3 h; a stored value that is no store has no ledger."""
    case = SCENARIOS['family']()
    stops = (Breakpoint('tank.tick.step[1]'),)
    water, ledger = Key('tank', ('water',)), Key('tank', ('water', 'external'))
    full = edited(case.program, Configuration(Request(7)), stops, (('tank.water', 5),))
    for keys in ((water,), (ledger,), (water, ledger)):
        request = Request(7, everything=False, keys=keys)
        for record in (
            edited(case.program, Configuration(request), stops, (('tank.water', 5),)),
            store.served(full, request),
        ):
            assert read(record, case.program, ['tank.water.external'], [1, 3])[0].values == (0, -1)
    with pytest.raises(KeyError, match=r'tank\.ticks is no store'):
        read(full, case.program, ['tank.ticks.external'], [1])


def test_a_value_before_the_run_after_its_horizon_or_after_its_stop_is_unavailable_with_the_reason():
    """The family's tank: nothing is read before 0 h or after the horizon of 7 h, and nothing after a
    stop at 2 h; each says why."""
    case = SCENARIOS['family']()
    record = run(case.program, case.configuration)
    before, after_ = read(record, case.program, ['tank.water'], [-1, 8])[0].values
    assert before == Unavailable('the record holds no value at -1 h: the run starts at 0 h')
    assert after_ == Unavailable('the record holds no value at 8 h: it reaches to its horizon, 7 h')
    stopped = run(case.program, case.configuration, (Breakpoint('tank.tick.step[1]'),)).record
    (late,) = read(stopped, case.program, ['tank.water'], [3])[0].values
    assert late.reason.startswith('the run stopped at 2 h at the breakpoint tank.tick.step[1]')


# ---- 10. each value with its own time -------------------------------------------------------------------


@pytest.mark.parametrize('seed', SEEDS)
def test_permuting_the_times_of_a_report_permutes_its_values(seed):
    """A report of the family at random times, some after its stop at a breakpoint and some twice,
    with a lag and a plain read: the values at a permutation of the times are the same permutation of
    the values."""
    rng = random.Random(seed)
    case = SCENARIOS['family']()
    stopped = rng.random() < 0.5
    record = (
        run(case.program, case.configuration, (Breakpoint('tank.tick.step[2]'),)).record
        if stopped
        else run(case.program, case.configuration)
    )
    times = [round(rng.uniform(0, 7), 2) for _ in range(5)]
    times += rng.sample(times, 2)
    order = rng.sample(range(len(times)), len(times))
    lags = {'tank.alarms': Lag(1, 2)}
    paths = ['tank.water', 'tank.alarms']
    first = report(record, case.program, case.configuration, paths, times, lags)
    again = report(record, case.program, case.configuration, paths, [times[k] for k in order], lags)
    for found, permuted in zip(first.values, again.values, strict=True):
        assert permuted.values == tuple(found.values[k] for k in order), seed


def test_a_stopped_run_asked_for_three_hours_then_one_gives_each_its_own_value():
    """Row 10: the family's tank stops at 2 h with 6 L; asked for [3, 1] the report gives nothing at
    3 h and the 8 L of 1 h at 1 h."""
    case = SCENARIOS['family']()
    stopped = run(case.program, case.configuration, (Breakpoint('tank.tick.step[1]'),))
    three, one = (
        report(stopped.record, case.program, case.configuration, ['tank.water'], [3, 1]).values[0].values
    )
    assert isinstance(three, Unavailable) and 'the record holds no value at 3 h' in three.reason
    assert one == pytest.approx(8)


# ---- 09. the proofs of an edited run ---------------------------------------------------------------------


def gated(rng):
    """A random gated plant: a stock pours into a tally at a random rate; a withdrawal moves 1 L out of
    the tally (or the stock) an hour after the yes/no `open` holds from 1 h, and nothing in the model
    writes `open`; a tick at 0.5 h, where a breakpoint stops the run; a random edit there: `open` on
    (most often), the tally lowered or raised, the stock lowered or raised, or none."""
    b = Builder(UNITS)
    drawn = rng.choice(['tally', 'stock'])
    b.entity(
        'plant',
        value('open', BOOL, False),
        value('stock', 'L', 10, lower=0),
        value('tally', 'L', 0, lower=0),
        value('spent', 'L', 0, lower=0),
        value('ticks', '', 0),
        value('alias', 'L', formula(this.tally)),
        value('gap', 'L', formula(this.tally - this.stock)),
        value('double', 'L', formula(this.tally * 2)),
        flow_of('pour', 'stock', 'tally', rng.choice([0.5, 1])),
        event(
            'withdraw',
            when(this.open & (t >= q(1, 'h')), start(this.withdraw), reset=reset_when(False)),
            after(q(1, 'h'), move(q(1, 'L'), getattr(this, drawn), this.spent)),
        ),
        event('tick', after(q(0.5, 'h'), add(this.ticks, 1))),
    )
    b.setup(start(named('plant').tick))
    edit = rng.choice(
        [
            *[(('plant.open', True),)] * 3,
            (('plant.tally', 0.1),),
            (('plant.tally', 3),),
            (('plant.stock', 1),),
            (('plant.stock', 12),),
            (),
        ]
    )
    return b.finish(), edit


@pytest.mark.parametrize('seed', SEEDS)
def test_no_proof_of_an_edited_run_is_contradicted_by_its_own_values(seed):
    """On a random gated plant edited at its stop: a lag that the report grants (its proof that the
    value never falls) holds a value that never falls in the record, read every 0.05 h; and an event
    that a trail says cannot start has no start in the trace."""
    rng = random.Random(seed)
    program, edit = gated(rng)
    configuration = Configuration(Request(4))
    record = edited(program, configuration, (Breakpoint('plant.tick.step[0]'),), edit)
    paths = ['plant.tally', 'plant.alias', 'plant.gap', 'plant.double', 'plant.stock', 'plant.spent']
    lags = {path: Lag(0.5, 1) for path in paths}
    found = report(record, program, configuration, paths, [4], lags)
    grid = [k * 0.05 for k in range(81)]
    for reported in found.values:
        if reported.lag is not None:
            # The record holds the run to its end (a move that would empty a tank fails it).
            values = [
                found
                for found in read(record, program, [reported.path], grid)[0].values
                if not isinstance(found, Unavailable)
            ]
            assert all(later >= earlier - 1e-9 for earlier, later in pairwise(values)), (seed, reported)
        for used in reported.trail:
            if used.kind == 'event' and used.why.startswith('it cannot start'):
                assert not record.entries('start', used.origin), (seed, used)


def test_an_edit_that_turns_on_a_withdrawal_withdraws_the_proofs_that_rest_on_its_event():
    """Row 09: a tally of 12 L that nothing drains but a withdrawal of 3 L that cannot start while
    `open` is false; an edit at 0.5 h opens it, the withdrawal runs at 2 h and the tally holds 9 L. The
    lags of the tally and of its alias are refused, each naming the edit, and the trail says the event
    started, which the edit made possible."""
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('open', BOOL, False),
        value('stock', 'L', 12, lower=0),
        value('spent', 'L', 0, lower=0),
        value('alias', 'L', formula(this.stock)),
        value('ticks', '', 0),
        flow_of('idle', None, 'stock', 0),
        event(
            'withdraw',
            when(this.open & (t >= q(1, 'h')), start(this.withdraw), reset=reset_when(False)),
            after(q(1, 'h'), move(q(3, 'L'), this.stock, this.spent)),
        ),
        event('tick', after(q(0.5, 'h'), add(this.ticks, 1))),
    )
    b.setup(start(named('plant').tick))
    program, configuration = b.finish(), Configuration(Request(4))
    record = edited(program, configuration, (Breakpoint('plant.tick.step[0]'),), (('plant.open', True),))
    assert read(record, program, ['plant.stock'], [1, 3])[0].values == pytest.approx((12, 9))
    lags = {'plant.stock': Lag(0.5, 1), 'plant.alias': Lag(0.5, 1)}
    for found in report(record, program, configuration, list(lags), [4], lags).values:
        assert found.lag is None and 'can fall' in found.note
        assert 'an edit at 0.5 h, at plant.tick.step[0], set plant.open from false to true' in found.note
        (withdraw,) = [
            used for used in found.trail if used.kind == 'event' and used.origin == 'plant.withdraw'
        ]
        assert withdraw.exercised and withdraw.why.startswith('it started at 1 h (an edit at 0.5 h')


# ---- 16. exercised is what was read --------------------------------------------------------------------


def tree(rng, kind, depth):
    """A random expression of `kind` (`number` or `yes/no`) as nested tuples, over the numbers n0..n3
    and the yes/nos b0..b2 of a member."""
    if depth == 0 or rng.random() < 0.3:
        if kind == 'number':
            return ('ref', f'n{rng.randrange(4)}') if rng.random() < 0.8 else ('const', rng.randint(0, 9))
        return ('ref', f'b{rng.randrange(3)}')
    if kind == 'number':
        op = rng.choice(['if', 'add', 'min', 'max'])
        if op == 'if':
            return (
                'if',
                tree(rng, 'yes/no', depth - 1),
                tree(rng, 'number', depth - 1),
                tree(rng, 'number', depth - 1),
            )
        return (op, tree(rng, 'number', depth - 1), tree(rng, 'number', depth - 1))
    op = rng.choice(['and', 'or', 'gt'])
    side = 'number' if op == 'gt' else 'yes/no'
    return (op, tree(rng, side, depth - 1), tree(rng, side, depth - 1))


def built(node):
    """The expression of the builder for a tree."""
    kind = node[0]
    if kind == 'ref':
        return getattr(this, node[1])
    if kind == 'const':
        return q(node[1], 'L')
    parts = [built(each) for each in node[1:]]
    if kind == 'if':
        return ifelse(*parts)
    if kind in ('min', 'max'):
        return (fmin if kind == 'min' else fmax)(*parts)
    return {
        'add': lambda a, c: a + c,
        'and': lambda a, c: a & c,
        'or': lambda a, c: a | c,
        'gt': lambda a, c: a > c,
    }[kind](*parts)


def evaluated(node, values, read_):
    """The value of a tree, as the spec evaluates it (a choice takes one side; `and` and `or` stop at
    the term that decides; `min`, `max`, a comparison and a sum read every operand), with each name
    that it reads added to `read_`."""
    kind = node[0]
    if kind == 'ref':
        read_.add(node[1])
        return values[node[1]]
    if kind == 'const':
        return node[1]
    if kind == 'if':
        return evaluated(node[2] if evaluated(node[1], values, read_) else node[3], values, read_)
    if kind == 'and':
        return evaluated(node[1], values, read_) and evaluated(node[2], values, read_)
    if kind == 'or':
        return evaluated(node[1], values, read_) or evaluated(node[2], values, read_)
    left, right = evaluated(node[1], values, read_), evaluated(node[2], values, read_)
    return {'add': left + right, 'min': min(left, right), 'max': max(left, right), 'gt': left > right}[kind]


@pytest.mark.parametrize('seed', range(60))
def test_the_exercised_values_of_a_formula_are_exactly_those_that_it_read(seed):
    """A random formula of choices, `and`, `or`, comparisons, sums, `min` and `max` over stored numbers
    and yes/nos that nothing writes: reported at 1 h, its value is the spec's, and the values of its
    trail that are exercised are exactly the names that its evaluation read; every other value it can
    read is not exercised, since the evaluation took another branch."""
    rng = random.Random(seed)
    values = {f'n{k}': rng.randint(0, 9) for k in range(4)} | {f'b{k}': rng.random() < 0.5 for k in range(3)}
    node = tree(rng, 'number', 4)
    expected = set()
    number = evaluated(node, values, expected)
    b = Builder(UNITS)
    parts = [value(name, 'L', number_) for name, number_ in values.items() if name.startswith('n')]
    parts += [value(name, BOOL, flag) for name, flag in values.items() if name.startswith('b')]
    b.entity(
        'm', *parts, value('f', 'L', formula(built(node) if node[0] != 'const' else built(node) + q(0, 'L')))
    )
    program, configuration = b.finish(), Configuration(Request(2))
    (found,) = report(run(program, configuration), program, configuration, ['m.f'], [1]).values
    assert found.values == (pytest.approx(number),)
    trail = {used.origin: used for used in found.trail if used.kind == 'value' and used.origin != 'm.f'}
    assert {origin for origin, used in trail.items() if used.exercised} == {f'm.{name}' for name in expected}
    for origin, used in trail.items():
        if origin[2:] not in expected:
            assert used.exercised is False and 'another branch' in used.why, (seed, origin)


@pytest.mark.parametrize('seed', range(30))
def test_a_status_display_exercises_the_case_that_applies_and_what_the_cases_before_it_read(seed):
    """A display of four cases on random tests over yes/nos (the last has none): at 1 h the case that
    applies is the first whose test holds; it alone is exercised, the cases before it read their
    tests and did not apply, the cases after it are not read, and the values exercised are those that
    the tests up to it read."""
    rng = random.Random(seed)
    values = {f'b{k}': rng.random() < 0.5 for k in range(3)} | {f'n{k}': k + 1 for k in range(4)}
    tests = [tree(rng, 'yes/no', 2) for _ in range(3)]
    expected, place = set(), 3
    for k, test in enumerate(tests):
        if evaluated(test, values, expected):
            place = k
            break
    b = Builder(UNITS)
    b.entity(
        'm',
        *(value(name, BOOL, flag) for name, flag in values.items() if name.startswith('b')),
        *(value(name, 'L', number) for name, number in values.items() if name.startswith('n')),
        status(
            *(rating('ok' if k % 2 else 'failed', built(test)) for k, test in enumerate(tests)), rating('ok')
        ),
    )
    program, configuration = b.finish(), Configuration(Request(2))
    (found,) = report(run(program, configuration), program, configuration, ['m.status'], [1]).values
    cases = {used.origin: used for used in found.trail if used.kind == 'case'}
    for k in range(4):
        used = cases[f'm.status.case[{k}]']
        assert used.exercised is (k == place), (seed, k, used)
        if k < place:
            assert used.why == 'its condition was read and did not hold at the reported times'
        elif k > place:
            assert 'not read' in used.why
    read_ = {used.origin[2:] for used in found.trail if used.kind == 'value' and used.exercised}
    assert read_ == expected, seed


def test_a_number_from_the_second_branch_does_not_cite_the_first():
    """Row 16: `chosen = a if high else b` with `high` false reads `high` and `b`: `a` is not exercised;
    a display whose first case always holds exercises that case and not its fallback."""
    b = Builder(UNITS)
    b.entity(
        'plant',
        input_('high', BOOL, False),
        value('a', 'L', 1),
        value('b', 'L', 2),
        value('chosen', 'L', formula(ifelse(this.high, this.a, this.b))),
        status(rating('ok', t >= q(0, 'h')), rating('failed')),
    )
    program, configuration = b.finish(), Configuration(Request(4))
    chosen, shown = report(
        run(program, configuration), program, configuration, ['plant.chosen', 'plant.status'], [2]
    ).values
    assert chosen.values == (pytest.approx(2),)
    exercised = {used.origin: used.exercised for used in chosen.trail}
    assert exercised['plant.a'] is False and exercised['plant.b'] and exercised['plant.high']
    cases = {used.origin: used.exercised for used in shown.trail if used.kind == 'case'}
    assert cases == {'plant.status.case[0]': True, 'plant.status.case[1]': False}


def test_a_flow_whose_request_reads_on_a_branch_is_exercised_as_the_record_shows():
    """A pump's request is `rate if open else idle`: with `open` true all along, the record shows that
    each evaluation read the rate and none the idle rate; with a level that moves, a branch on it is
    one that the record cannot show: the trail says neither (None)."""
    b = Builder(UNITS)
    b.entity(
        'pump',
        value('open', BOOL, True),
        input_('rate', 'L/h', 2),
        input_('idle', 'L/h', 0),
        input_('slow', 'L/h', 1),
        value('level', 'L', 10, lower=0),
        value('out', 'L', 0, lower=0),
        flow_of_request('serve', ifelse(this.open, this.rate, this.idle)),
        flow_of_request('drain', ifelse(this.level > q(5, 'L'), this.slow, q(0, 'L/h')), source='level'),
    )
    program, configuration = b.finish(), Configuration(Request(4))
    (found,) = report(run(program, configuration), program, configuration, ['pump.out'], [4]).values
    trail = {used.origin: used for used in found.trail}
    assert trail['pump.rate'].exercised is True
    assert trail['pump.idle'].exercised is False and trail['pump.idle'].why.startswith(
        'the run did not read it'
    )
    assert trail['pump.slow'].exercised is None and 'does not show' in trail['pump.slow'].why


def test_a_lag_with_no_window_in_the_run_exercises_nothing_that_its_formula_reads():
    """`double = 2 tally` lagged by 1 h to 2 h at 1 h reads before the run: the report holds no value,
    and its trail says that nothing that the formula reads was read."""
    b = Builder(UNITS)
    b.entity(
        'm',
        value('tally', 'L', 0, lower=0),
        value('double', 'L', formula(this.tally * 2)),
        flow_of('fill', None, 'tally', 1),
    )
    program, configuration = b.finish(), Configuration(Request(4))
    lags = {'m.double': Lag(1, 2)}
    (found,) = report(run(program, configuration), program, configuration, ['m.double'], [1], lags).values
    assert isinstance(found.values[0], Unavailable)
    (tally,) = [used for used in found.trail if used.origin == 'm.tally']
    assert tally.exercised is False and tally.why.endswith('the report holds no value of the value there')


def flow_of_request(name, request, source=None):
    """A flow into `out` (from SOURCE, or the store `source`) at a request that is a formula."""
    from napkin.program.build import flow

    return flow(name, SOURCE if source is None else getattr(this, source), this.out, request=formula(request))


# ---- 21. only a number is lagged ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('declared', 'kind'),
    [
        (input_('flag', BOOL, False), 'a yes/no'),
        (input_('flag', TEXT, 'north'), 'a text'),
        (value('flag', BOOL, True), 'a yes/no'),
    ],
    ids=['input yes/no', 'input text', 'stored yes/no'],
)
def test_a_lag_of_what_is_no_number_is_refused_by_name_and_the_plain_read_stays(declared, kind):
    """Row 21: a lag of `false`, of a text or of a stored yes/no is refused, naming what the value is;
    the plain read stays."""
    b = Builder(UNITS)
    b.entity('plant', declared)
    program, configuration = b.finish(), Configuration(Request(4))
    (found,) = report(
        run(program, configuration), program, configuration, ['plant.flag'], [4], {'plant.flag': Lag(1, 2)}
    ).values
    assert (
        found.lag is None
        and found.note == f'the lag is refused: plant.flag is {kind}, and a lag averages a number'
    )
    assert found.values == (declared.init if not hasattr(declared.init, 'node') else found.values[0],)


# ---- 18. the budget of pieces --------------------------------------------------------------------------


@pytest.mark.parametrize('pieces', [1, 2, 3, 5, 8, 13, 40])
def test_a_record_holds_at_most_its_budget_and_agrees_with_the_whole_run_before_its_end(pieces):
    """The family to its horizon of 7 h, recorded within a budget: the values that the record holds
    have at most that many pieces; before the end of the record every value is the whole run's; from
    it on each is unavailable with the budget's reason. A cut of the whole record by the same request
    ends at the same time."""
    case = SCENARIOS['family']()
    whole = run(case.program, case.configuration)
    request = Request(7, pieces=pieces)
    budgeted = run(case.program, Configuration(request))
    assert sum(len(history.pieces) for history in budgeted.histories) <= pieces
    assert store.served(whole, request).end == budgeted.end
    paths = ['tank.water', 'tank.ticks', 'tank.alarms']
    times = [k * 0.25 for k in range(29)]
    for path in paths:
        (expected,) = read(whole, case.program, [path], times)
        (found,) = read(budgeted, case.program, [path], times)
        for at, value_, exact in zip(times, found.values, expected.values, strict=True):
            if budgeted.failure is None or at < budgeted.end:
                assert same(value_, exact), (pieces, path, at)
            else:
                assert isinstance(value_, Unavailable) and 'budget' in value_.reason, (pieces, path, at)


def test_a_budget_of_one_piece_stops_the_record_by_name_at_a_pause_and_at_the_end():
    """Row 18: with a budget of one piece the family's record, whole or of the stock alone, at a pause
    or to its end, holds one piece at most and names the budget."""
    case = SCENARIOS['family']()
    water = Key('tank', ('water',))
    for request in (Request(7, pieces=1), Request(7, everything=False, keys=(water,), pieces=1)):
        configuration = Configuration(request)
        paused = run(case.program, configuration, (Breakpoint('tank.tick.step[2]'),)).record
        ended = run(case.program, configuration)
        for record in (paused, ended):
            assert (
                sum(len(history.pieces) for history in record.histories if record.manifest.names(history.key))
                <= 1
            )
            assert record.failure.detail('budget') == 1 and 'budget of 1 piece' in record.stopped()


# ---- 15. no recursion in the reader ---------------------------------------------------------------------------


def test_a_total_through_a_long_chain_of_child_links_reads_without_recursion():
    """Row 15: each of 300 nodes adds its own 1 L to the totals of its children, and each but the last
    has the next node as its one child: the first node's total is 300 L. And a chain of 3,000 formulas,
    each 1 L more than the one before, reads 3,000 L at its end."""
    b = Builder(UNITS)
    node = b.template(
        'Node',
        value('own', 'L', 1),
        value('kids', group_of('Node'), literal()),
        value('total', 'L', formula(this.own + fsum(this.kids.total))),
    )
    count_ = 300
    for k in range(count_):
        b.member(node, f'n{k:03d}', **({'kids': literal(named(f'n{k + 1:03d}'))} if k + 1 < count_ else {}))
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert read(record, program, ['n000.total'], [1])[0].values == (pytest.approx(300),)
    b = Builder(UNITS)
    chain = [
        value('v0', 'L', 1),
        *(value(f'v{k}', 'L', formula(getattr(this, f'v{k - 1}') + q(1, 'L'))) for k in range(1, 3000)),
    ]
    b.entity('chain', *chain)
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert read(record, program, ['chain.v2999'], [1])[0].values == (pytest.approx(3000),)


def test_a_reference_to_an_occurrence_is_no_value_of_a_record_or_a_report():
    """A check saves a reference to the newest repair (`job`): no record holds the reference, so a read
    and a report of its path are refused by name, pointing to the occurrence's own path."""
    from napkin.program.record import Manifest, Record
    from tests.language.test_events import LIVES, program_of

    program = program_of(LIVES.format(stage='                this.held = job.amount'))
    record, configuration = Record(Manifest(10)), Configuration(Request(10))
    for asked in (
        lambda: read(record, program, ['crew.check#0.job'], [2]),
        lambda: report(record, program, configuration, ['crew.check#0.job'], [2]),
    ):
        with pytest.raises(
            KeyError, match=r'a reference to an occurrence of crew\.repair is no value that a record holds'
        ):
            asked()
