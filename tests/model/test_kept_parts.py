"""A structure keeps every part that one of its parts names (docs/python-api.md, "The parts that cannot act").

A structure leaves out the parts that cannot act in its runs. Every part that it keeps keeps the parts
that it reads or changes: a flow keeps its ends and what its rate reads, also when its rate is zero in
every state that the runs reach; a stock keeps what its start value, its bounds and its rate read; a
sum check keeps what its total and its tolerance read; and a rule keeps what its trigger and its step
read and change. An event that a kept part counts or times stays when the rules that emit it are left
out: it never happens, so its count stays 0.

The files are synthetic. Each expectation is a closed form of inputs read from the model, a
property (the whole structure, with every part, gives the run's numbers), or the independent check
below that every name of a built structure resolves.
"""

from __future__ import annotations

import random

import pytest

from napkin.engine import evaluate_study, sample_result
from napkin.engine.report import evaluate_outputs
from napkin.engine.runtime import simulate
from napkin.expressions import names_in
from tests import build as tb
from tests.helpers import SCENARIO_IDS, catalogue_model

LIB = tb.library()
CLOSED = '0 people/h'
ELAPSED = tb.output('elapsed_time', 't', 'h', 'level', doc='Elapsed time')
# The menu and the runs of a file whose attacker may keep its access: run `a` without it, run `b` with
# the profile `Keeps access`, which sets the state `s.access` to "kept" at the start.
ACCESS = (
    tb.DEFAULT_OPTIONS,
    tb.options(
        'Access',
        tb.option('No access', 'No access.'),
        tb.option('Keeps access', 'The attacker keeps its access.', f's.access = "kept"  {tb.BASIS}'),
    ),
)
ACCESS_RUNS = tb.runs(a=['Default', 'No access'], b=['Default', 'Keeps access'])


def with_access(*members, outputs=(ELAPSED,), others=()):
    """A file around entity `s`, as `tests.build.system` writes it, with these members, the entities
    `others` and the top-level `outputs`, and the menu and runs of the access (`ACCESS`)."""
    return tb.document(
        'Numerical fixture',
        tb.entity('s', *members, title='System'),
        *others,
        *outputs,
        horizon=10,
        option_groups=ACCESS,
        run_lines=ACCESS_RUNS,
    )


def gate_parts():
    """([values], [events]) of a gate that only the attacker's access opens, `open_time` after the
    start."""
    values = [
        tb.named('access', 'none', 'kept'),
        tb.named('gate', 'shut', 'open'),
        tb.parameter('open_time', 2, 'h', 1, 4, doc='Time until the gate opens'),
        tb.parameter('rate', 5, 'people/h', 1, 10, doc='Rate'),
    ]
    events = [tb.event('breach', 'access is "kept" and t >= open_time', 'gate = "open"')]
    return values, events


def drain_parts(status=False):
    """([values], [status], [events and flows]) of the drain (`drain`)."""
    values, events = gate_parts()
    values += [
        tb.stock('store', 100, 'people', size=100, doc='Store'),
        tb.stock('sink', 0, 'people', size=100, doc='Sink'),
    ]
    events.append(tb.flow('drain', 'store -> sink', f'rate if gate is "open" else {CLOSED}'))
    shows = [tb.status(('degraded', 'gate is "open"', 'Open'), ('ok', None, 'Shut'))] if status else []
    return values, shows, events


MOVED = (tb.output('moved', 's.sink', 'people', 'level', doc='Moved'),)


def drain(status=False):
    """A store drains into a sink at `rate` while the gate is open. Without the access the gate stays
    shut, so the drain never moves: the gate and the sink stay for it. With `status`, the system's
    status also reads the gate."""
    values, shows, events = drain_parts(status)
    return with_access(*values, *shows, *events, outputs=MOVED)


def final(model, study, output):
    """{run: the final value of an output of the file} of an admitted study."""
    report = sample_result(study)
    return {
        run: item['reporting_points']['final']['values'][model.outputs[output]]
        for run, item in report['runs'].items()
    }


@pytest.mark.parametrize('status', [False, True])
def test_a_flow_that_never_moves_keeps_its_ends_and_what_its_rate_reads(status):
    """Without the access the drain's rate is zero in every state that the runs reach. The drain stays,
    so the gate that its rate reads and the sink that it fills stay too; with the access, the drain
    moves `rate` from `open_time` to the end of the run (at most 10 people an hour for 9 hours, so the
    store of 100 never runs out)."""
    model = tb.compiled(drain(status))
    kept = model.structure_of('a')
    assert {'s.gate', 's.sink'} <= set(kept.modes) | set(kept.quantities)
    assert 's.drain' in kept.flows
    study = evaluate_study(model)
    assert study.admissible, study.diagnostics
    values = model.run_values('b')
    expected = values['s.rate'] * (model.time['horizon'] - values['s.open_time'])
    assert final(model, study, 'moved') == pytest.approx({'a': 0.0, 'b': expected}, abs=1e-9)


def counted():
    """`all_clear` rings an alarm at `clear_time` if the breach has not happened. Without the access the
    breach cannot happen, and its rule is left out; its event stays, with a count of 0, because
    `all_clear`, the system's status and an output read it."""
    values, events = gate_parts()
    values += [
        tb.named('alarm', 'quiet', 'ringing'),
        tb.parameter('clear_time', 6, 'h', 5, 8, doc='Time of the all-clear'),
    ]
    events.append(tb.event('all_clear', 'count(breach) is 0 and t >= clear_time', 'alarm = "ringing"'))
    shows = tb.status(('degraded', 'count(breach) > 0', 'Breached'), ('ok', None, 'Clear'))
    breaches = tb.output(
        'breaches', 'count(s.breach)', 'fraction', 'level', doc='Breaches', under=('signed',)
    )
    return with_access(*values, shows, *events, outputs=(breaches,))


def test_an_event_that_never_happens_keeps_its_count_for_the_parts_that_read_it():
    model = tb.compiled(counted())
    assert 's.breach' in model.left_out[()]['rules']
    assert not model.structure_of('a').events[model.events['s.breach']].sources
    study = evaluate_study(model)
    assert study.admissible, study.diagnostics
    values = model.run_values('a')
    assert values['s.open_time'] < values['s.clear_time']
    fired = {
        run: [(entry['t'], entry['event']) for entry in study.runs[run]['trajectory'].trace] for run in 'ab'
    }
    # Without the access only the all-clear happens; with it the breach comes first, and no all-clear.
    assert fired['a'] == [(pytest.approx(values['s.clear_time']), 's.all_clear.done')]
    assert fired['b'] == [(pytest.approx(values['s.open_time']), 's.breach.done')]
    assert final(model, study, 'breaches') == {'a': 0, 'b': 1}


def rationed():
    """A pool that two flows draw on, in proportion up to `rate`, while the gate is open, and that a
    third fills from outside. Without the access every one of the three flows is still: the pool,
    which starts empty, stays because they draw on it."""
    values, events = gate_parts()
    names = ('pool', 'left', 'right')
    values += [tb.stock(name, 0, 'people', size=100, doc=name.capitalize()) for name in names]
    opened = f'rate if gate is "open" else {CLOSED}'
    events += [
        tb.flow('fill', tb.move(None, 'pool'), opened),
        tb.flow('to_left', 'pool -> left', opened),
        tb.flow('to_right', 'pool -> right', opened),
        tb.share('pool', 'rate'),
    ]
    outputs = tuple(tb.output(name, f's.{name}', 'people', 'level', doc=name.capitalize()) for name in names)
    return with_access(*values, *events, outputs=outputs)


def test_a_rationed_stock_stays_while_the_flows_that_draw_on_it_stay():
    """The pool holds what the fill brings in and the two flows have not yet taken out: in each run,
    pool + left + right is the inflow, `rate` from `open_time` with the access and nothing without it."""
    model = tb.compiled(rationed())
    assert 's.pool' in model.structure_of('a').quantities
    assert 's.share_pool' in model.structure_of('a').allocation
    study = evaluate_study(model)
    assert study.admissible, study.diagnostics
    totals = {
        run: sum(final(model, study, name)[run] for name in ('pool', 'left', 'right')) for run in ('a', 'b')
    }
    values = model.run_values('b')
    inflow = values['s.rate'] * (model.time['horizon'] - values['s.open_time'])
    assert totals == pytest.approx({'a': 0.0, 'b': inflow}, rel=1e-6, abs=1e-6)


def tolerant():
    """The drain, with a sum check whose tolerance reads a state that nothing else reads and no step
    changes."""
    values, shows, events = drain_parts()
    values.append(tb.named('precision', 'fine', 'coarse'))
    check = tb.check(
        'store + sink is 100 people',
        'Every person is in the store or the sink.',
        within='0.001 people if precision is "fine" else 0.1 people',
    )
    return with_access(*values, *shows, *events, check, outputs=MOVED)


def skipped():
    """With the access, a waiting event asks for a light an hour after `open_time`, but only if the
    system is armed, which it never is: the event always ends skipped. Its outcome `done`, which turns
    on the system's light and fires the lamp's event, can never happen, and the structure keeps what
    it changes: the light. Every name of the structure resolves, also the line that fires the lamp's
    event."""
    values, events = gate_parts()
    values += [tb.named('armed', 'no', 'yes'), tb.named('light', 'off', 'on')]
    events.append(
        tb.event(
            'ask',
            't >= open_time',
            'light = "on"',
            'lamp.turn_on',
            after='1 h',
            keep='access is "kept"',
            condition='armed is "yes"',
            do_records=tb.BASIS,
        )
    )
    lamp = tb.entity(
        'lamp',
        tb.named('glow', 'off', 'on'),
        tb.named_event('turn_on', 'glow = "on"', records=None),
        doc='A lamp.',
    )
    return with_access(*values, *events, others=(lamp,))


def test_a_step_that_never_commits_keeps_what_it_changes():
    model = tb.compiled(skipped())
    kept = model.structure_of('b')
    assert 's.light' in kept.modes
    for structure in model.structures.values():
        assert not unresolved(structure)
    study = evaluate_study(model)
    assert study.admissible, study.diagnostics
    values = model.run_values('b')
    trace = study.runs['b']['trajectory'].trace
    assert [entry['t'] for entry in trace if entry['event'] == 's.ask.skipped'] == [
        pytest.approx(values['s.open_time'] + 1)
    ]


def test_a_sum_check_keeps_what_its_tolerance_reads():
    model = tb.compiled(tolerant())
    for structure in model.structures.values():
        assert 's.precision' in structure.modes
    assert evaluate_study(model).admissible


# ---- every name of a built structure resolves --------------------------------------------------------


def step_names(step):
    """(the names that a flat step reads, the values that it changes)."""
    reads, writes = set(), set()
    for target, value in step.set.items():
        writes.add(target)
        reads |= names_in(value.expr) if value.expr is not None else set()
    for item in step.transfer:
        writes |= {item.source, item.target}
        reads |= names_in(item.amount)
    return reads, writes


def unresolved(s):
    """{part: names} of the names that a part of a flat structure reads or changes and the structure
    does not have. Written from the structure's sections (docs/python-api.md, "The structure")."""
    values = {'t'} | set(s.parameters) | set(s.quantities) | set(s.computed) | set(s.labels)
    values |= set(s.modes) | {f'{m}__entered' for m in s.modes}
    values |= {f'{e}{suffix}' for e in s.events for suffix in ('__count', '__time')}
    found = {}

    def need(part, names, known):
        if set(names) - known:
            found.setdefault(part, set()).update(set(names) - known)

    for q in s.quantities.values():
        for bound in (q.initial, q.minimum, q.maximum):
            if isinstance(bound, str):
                need(q.path, names_in(bound), values)
    for qid, rate in s.rates.items():
        need(rate.path, names_in(rate.expr) | {qid}, values)
    for item in s.computed.values():
        need(item.path, names_in(item.expr), values)
    for label in s.labels.values():
        for case in label.cases:
            need(label.path, names_in(case.when), values)
    for flow in s.flows.values():
        ends = {end for end in (flow.source, flow.target) if end is not None}
        need(flow.path, names_in(flow.rate) | ends, values)
        need(flow.path, {flow.allocation} if flow.allocation is not None else set(), set(s.allocation))
    for group in s.allocation.values():
        need(group.path, names_in(group.capacity), values)
        need(group.path, set(group.order or ()), set(s.flows))
    for group in s.coupling.values():
        need('coupling', set(group.flows), set(s.flows))
    for rid, rule in s.rules.items():
        need(rid, names_in(rule.trigger.when), values)
        for text in (*(rule.each or ()), rule.keep):
            need(rid, names_in(text) if text else set(), values)
        # The values that the rule reads at a firing (a draw, a delayed value) read the structure, and
        # its delay, chances and lines read them by their placeholders.
        firing = values | {item.name for item in rule.extras or ()}
        for item in rule.extras or ():
            texts = [item.expr, item.delay, *(item.args or {}).values()]
            need(rid, set().union(*(names_in(x) for x in texts if x)), values)
        need(rid, names_in(rule.delay) if rule.delay else set(), firing)
        for outcome in rule.outcomes:
            chance = outcome.chance
            need(rid, names_in(chance) if isinstance(chance, str) and chance != 'else' else set(), firing)
            reads, writes = step_names(outcome.do)
            need(rid, reads | writes, firing)
            # The events that an outcome's lines fire are rules of the structure.
            need(rid, set(outcome.do.fire), set(s.rules))
    for section in ('input_checks', 'state_checks'):
        for item in s.section(section).values():
            need(item.path, names_in(item.expr), values)
    for p in s.partitions.values():
        need(p.path, set(p.parts) | names_in(p.total) | names_in(p.tolerance or '0'), values)
    for oid, outcome in s.outcomes.items():
        lag = outcome.lag
        texts = [outcome.expr]
        if lag is not None:
            texts += [lag.delay, lag.minimum, lag.maximum, *(c.delay for c in lag.components or ())]
        need(oid, set().union(*(names_in(x) for x in texts if x)), values | set(s.outcomes))
    for event in s.events.values():
        need('events', set(event.sources), set(s.rules))
    return found


@pytest.mark.scenario_contract
def test_every_name_of_each_catalogue_structure_resolves():
    for sid in SCENARIO_IDS:
        model = catalogue_model(sid)
        for starts, structure in model.structures.items():
            assert not unresolved(structure), (sid, starts)


CONDITIONS = ('gate is "open"', 'level is "high"', 'level is not "high"', 'true')


def random_document(rng):
    """A small random file around the gate: a second state that an event raises, an event that counts
    the breach, stocks of which some start empty, flows between them that a condition opens, an
    optional status and sum check, and an output for each stock and for the breaches."""
    values, events = gate_parts()
    values += [
        tb.named('level', 'low', 'high'),
        tb.parameter('later', 6, 'h', 5, 7, doc='Time of the second step'),
    ]
    initial = {name: 100 if name == 'store' else rng.choice([0, 0, 10]) for name in ('store', 'a', 'b', 'c')}
    values += [tb.stock(name, start, 'people', size=100) for name, start in initial.items()]
    raised = rng.choice(['gate is "open" and ', 'count(breach) is 0 and ', ''])
    # The event that raises the level: `raise`, a word of Python, is no name.
    events.append(tb.event('raise_level', f'{raised}t >= later', 'level = "high"'))
    pairs = [('store', 'a'), ('a', 'b'), ('b', 'c'), ('store', 'c')]
    for i, (source, target) in enumerate(rng.sample(pairs, rng.randint(1, len(pairs)))):
        when = rng.choice(CONDITIONS)
        # The rate vanishes with its source, so no two flows out of one stock need an allocation.
        rate = f'{source} / 4 h' if when == 'true' else f'{source} / 4 h if {when} else {CLOSED}'
        events.append(tb.flow(f'flow{i}', f'{source} -> {target}', rate))
    inflow = rng.random() < 0.5
    if inflow:
        when = rng.choice(CONDITIONS)
        events.append(
            tb.flow(
                'inflow', tb.move(None, 'c'), f'rate if {when} else {CLOSED}' if when != 'true' else 'rate'
            )
        )
    shows = []
    if rng.random() < 0.5:
        shows.append(tb.status(('degraded', rng.choice(CONDITIONS[:3]), 'Changed'), ('ok', None, 'Usual')))
    outputs = [tb.output(name, f's.{name}', 'people', 'level', doc=name) for name in ('store', 'a', 'b', 'c')]
    outputs.append(
        tb.output('breaches', 'count(s.breach)', 'fraction', 'level', doc='Breaches', under=('signed',))
    )
    checks = []
    if not inflow and rng.random() < 0.5:
        total = sum(initial.values())
        checks.append(
            tb.check(
                f'store + a + b + c is {tb.q(total, "people")}',
                'Every person is in one stock.',
                within=f'0.001 people if {rng.choice(CONDITIONS[:3])} else 0.01 people',
            )
        )
    return with_access(*values, *shows, *events, *checks, outputs=outputs)


def outputs_at_end(model, structure, run):
    """The final value of every output of one run in `structure`, resolved with the run's values."""
    numbers, errors = model.numbers(model.run_values(run))
    assert not errors
    rs = model.resolve_in(structure, numbers, f'run {run}')
    trajectory = simulate(rs, LIB)
    (row,) = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, LIB, [trajectory.horizon])
    return row['values']


def test_random_documents_build_resolve_and_run_as_their_whole_structures():
    rng = random.Random(20261015)
    left_out = 0
    for _ in range(60):
        source = random_document(rng)
        model = tb.compiled(source, LIB)
        for starts, structure in model.structures.items():
            assert not unresolved(structure), (starts, source)
            left_out += sum(map(len, model.left_out[starts].values()))
        for run, info in model.runs.items():
            ran = outputs_at_end(model, model.structures[info['starts']], run)
            whole = outputs_at_end(model, model.whole[info['starts']], run)
            assert ran == pytest.approx(whole, rel=1e-9, abs=1e-9), (run, source)
    # The documents do leave parts out: the property is not empty.
    assert left_out > 0


def test_an_entity_that_only_its_own_sum_check_reads_is_left_out():
    # Two empty stocks that nothing moves; the entity's sum check reads them and nothing else does.
    def idle(*checks):
        text = tb.document(
            'Numerical fixture',
            tb.entity('s', title='System'),
            tb.entity(
                'idle', tb.stock('a'), tb.stock('b'), *checks, doc='Two empty stocks that nothing moves.'
            ),
            ELAPSED,
            horizon=1,
        )
        return tb.compiled(text)

    # A sum check says how close its sum holds; without `within` the assert would be a plain check.
    check = tb.check('a + b is 0 people', 'Empty.', within='0.001 people')
    for model in (idle(), idle(check)):
        assert all('idle' in left['entities'] for left in model.left_out.values())
